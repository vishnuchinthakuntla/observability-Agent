


"""
DYNAMIC AGENT EVALUATION FRAMEWORK
=========================================
1. Ask for agent name only
2. Filter observations by agent_name
3. Auto-detect project_id from traces table
4. Store both agent_name and project_id in evaluation_results
5. Calculate averages ONLY at project level (NO NULL rows)
6. Store averages with both agent_name and project_id
"""

import asyncio
import json
import os
from uuid import uuid4
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

from dotenv import load_dotenv
load_dotenv()  # Load variables from .env into the environment

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from deepeval.test_case import LLMTestCase, SingleTurnParams
from deepeval.metrics import GEval, ToxicityMetric
from deepeval.models import AzureOpenAIModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =====================================================
# DATABASE CONFIGURATION
# =====================================================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Check your .env file.")
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# =====================================================
# AZURE OPENAI MODEL
# =====================================================

_azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
_azure_base_url = os.getenv("AZURE_OPENAI_BASE_URL")
_azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
_azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini-prod")

if not _azure_api_key or not _azure_base_url:
    raise RuntimeError(
        "Azure OpenAI credentials are missing. "
        "Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_BASE_URL in your .env file."
    )

azure_model = AzureOpenAIModel(
    model=_azure_deployment,
    api_key=_azure_api_key,
    base_url=_azure_base_url,
    api_version=_azure_api_version,
    deployment_name=_azure_deployment,
)

# =====================================================
# GET METRICS FROM DATABASE
# =====================================================

async def get_all_metrics_from_master() -> List[Dict[str, Any]]:
    """
    Fetch all active metrics from metric_master table
    """
    query = text("""
        SELECT 
            id,
            metric_name,
            metric_description,
            default_threshold as threshold,
            category
        FROM metric_master
        WHERE active = true
        ORDER BY metric_name
    """)

    async with SessionLocal() as session:
        result = await session.execute(query)
        return [dict(row) for row in result.mappings().all()]

# =====================================================
# BUILD METRICS DYNAMICALLY
# =====================================================

def create_metric_from_master(metric_name: str, metric_description: str, threshold: float):
    """
    Create DeepEval metric dynamically from metric_master data
    """
    # Special handling for Toxicity
    if metric_name.lower() == 'toxicity':
        metric = ToxicityMetric(threshold=threshold, model=azure_model)
        metric.name = metric_name
        return metric

    # For all other metrics, use GEval
    return GEval(
        name=metric_name,
        criteria=metric_description,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        model=azure_model,
        threshold=threshold
    )

async def build_metrics_from_master() -> List[tuple]:
    """
    Build all metrics from metric_master
    Returns list of (metric_name, metric_object, threshold) tuples
    """
    metrics_data = await get_all_metrics_from_master()

    if not metrics_data:
        logger.warning("No metrics found in metric_master")
        return []

    metrics = []
    for metric_row in metrics_data:
        metric_name = metric_row['metric_name']
        metric_description = metric_row['metric_description']
        threshold = float(metric_row['threshold'])

        try:
            metric_obj = create_metric_from_master(metric_name, metric_description, threshold)
            metrics.append((metric_name, metric_obj, threshold))
            logger.info(f"✅ Created metric: {metric_name} (threshold: {threshold})")
        except Exception as e:
            logger.error(f"❌ Failed to create metric '{metric_name}': {e}")

    return metrics

# =====================================================
# FETCH UNEVALUATED OBSERVATIONS - FILTER BY AGENT
# =====================================================

async def get_unevaluated_observations(agent_name: str, limit: int = 100) -> List[Dict]:
    """
    Fetch unevaluated observations filtered by agent_name
    Auto-joins with traces table to get project_id
    """
    query = text("""
        SELECT 
            o.id, 
            o.trace_id, 
            o.input, 
            o.output, 
            o.name as agent_name,
            t.project_id
        FROM observations o
        LEFT JOIN traces t ON o.trace_id = t.id
        WHERE o.name = :agent_name
        AND o.evaluated = false
        ORDER BY o.created_at ASC
        LIMIT :limit
    """)

    async with SessionLocal() as session:
        result = await session.execute(query, {"agent_name": agent_name, "limit": limit})
        rows = result.mappings().all()

        # Log what we found
        if rows:
            logger.info(f"   Found {len(rows)} unevaluated observations for agent: {agent_name}")
            for row in rows:
                project_id = row.get('project_id')
                if project_id:
                    logger.info(f"   - Observation {row['id'][:8]}... Project: {project_id}")
                else:
                    logger.warning(f"   - Observation {row['id'][:8]}... Project: NULL")

        return [dict(row) for row in rows]

# =====================================================
# EVALUATE OBSERVATION - ALL METRICS IN PARALLEL
# =====================================================

async def evaluate_observation(
    agent_input: Any,
    agent_output: Any,
    metrics: List[tuple]
) -> Dict[str, Dict]:
    """
    Evaluate a single observation with all metrics in PARALLEL
    """

    def to_str(value) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, indent=2) if value else ""

    # Create test case
    test_case = LLMTestCase(
        input=to_str(agent_input),
        actual_output=to_str(agent_output)
    )

    # Get all metric objects
    metric_objects = [metric_obj for _, metric_obj, _ in metrics]

    # Run ALL metrics in PARALLEL
    try:
        await asyncio.gather(*[
            metric_obj.a_measure(test_case, _show_indicator=False)
            for metric_obj in metric_objects
        ])
    except Exception as e:
        logger.error(f"Error during metric evaluation: {e}")
        raise

    # Collect results
    results = {}
    for metric_name, metric_obj, threshold in metrics:
        score = float(metric_obj.score) if metric_obj.score is not None else 0.0
        reason = getattr(metric_obj, "reason", "") or ""
        passed = score >= threshold
        results[metric_name] = {
            "score": score,
            "reason": reason,
            "threshold": threshold,
            "passed": passed
        }

    return results

# =====================================================
# SAVE EVALUATION RESULTS WITH AGENT + PROJECT
# =====================================================

async def save_evaluation_results(
    observation_id: str,
    trace_id: str,
    agent_name: str,
    project_id: Optional[str],
    results: Dict[str, Dict]
):
    """
    Save evaluation results with both agent_name and project_id
    """
    query = text("""
        INSERT INTO evaluation_results
            (id, observation_id, trace_id, agent_name, project_id, metric_name, 
             score, reason, threshold, passed, evaluated_at)
        VALUES
            (:id, :observation_id, :trace_id, :agent_name, :project_id, :metric_name,
             :score, :reason, :threshold, :passed, NOW())
    """)

    async with SessionLocal() as session:
        for metric_name, metric_result in results.items():
            await session.execute(query, {
                "id": str(uuid4()),
                "observation_id": observation_id,
                "trace_id": trace_id,
                "agent_name": agent_name,
                "project_id": project_id,
                "metric_name": metric_name,
                "score": float(metric_result["score"]),
                "reason": metric_result["reason"],
                "threshold": float(metric_result["threshold"]),
                "passed": metric_result["passed"]
            })
        await session.commit()
        logger.info(f"✅ Saved: {agent_name} | Project: {project_id or 'NULL'} | Observation: {observation_id[:8]}...")

# =====================================================
# MARK OBSERVATION AS EVALUATED
# =====================================================

async def mark_observation_evaluated(observation_id: str):
    """
    Mark observation as evaluated
    """
    query = text("""
        UPDATE observations
        SET evaluated = true
        WHERE id = :id
    """)

    async with SessionLocal() as session:
        await session.execute(query, {"id": observation_id})
        await session.commit()
        logger.info(f"✅ Marked evaluated: {observation_id[:8]}...")

# =====================================================
# CALCULATE AND SAVE AVERAGES - PROJECT LEVEL ONLY (NO NULL)
# =====================================================

async def calculate_and_save_averages(agent_name: str, project_id: str):
    """
    Calculate daily averages for agent and project
    Saves to averages table with both agent_name and project_id
    ONLY saves project-level averages (NO NULL rows)
    """
    logger.info(f"\n📊 Calculating averages: {agent_name} | Project: {project_id}")

    query = text("""
        WITH observation_metrics AS (
            SELECT 
                observation_id,
                MAX(CASE WHEN metric_name = 'Relevancy' THEN score END) as relevancy_score,
                MAX(CASE WHEN metric_name = 'Safety' THEN score END) as safety_score,
                MAX(CASE WHEN metric_name = 'Coherence' THEN score END) as coherence_score,
                MAX(CASE WHEN metric_name = 'Helpfulness' THEN score END) as helpfulness_score,
                MAX(CASE WHEN metric_name = 'Toxicity' THEN score END) as toxicity_score,
                MAX(CASE WHEN metric_name = 'Relevancy' THEN threshold END) as relevancy_threshold,
                MAX(CASE WHEN metric_name = 'Safety' THEN threshold END) as safety_threshold,
                MAX(CASE WHEN metric_name = 'Coherence' THEN threshold END) as coherence_threshold,
                MAX(CASE WHEN metric_name = 'Helpfulness' THEN threshold END) as helpfulness_threshold,
                MAX(CASE WHEN metric_name = 'Toxicity' THEN threshold END) as toxicity_threshold
            FROM evaluation_results
            WHERE agent_name = :agent_name
            AND project_id = :project_id
            AND DATE(evaluated_at) = CURRENT_DATE
            GROUP BY observation_id
        )
        SELECT 
            AVG(relevancy_score) as relevancy_avg,
            AVG(safety_score) as safety_avg,
            AVG(coherence_score) as coherence_avg,
            AVG(helpfulness_score) as helpfulness_avg,
            AVG(toxicity_score) as toxicity_avg,
            COUNT(*) as total_evaluated,
            SUM(CASE 
                WHEN relevancy_score >= relevancy_threshold 
                AND safety_score >= safety_threshold 
                AND coherence_score >= coherence_threshold 
                AND helpfulness_score >= helpfulness_threshold 
                AND toxicity_score <= toxicity_threshold 
                THEN 1 ELSE 0 END) as passed_count
        FROM observation_metrics
    """)

    async with SessionLocal() as session:
        result = await session.execute(query, {"agent_name": agent_name, "project_id": project_id})
        row = result.mappings().first()

        if not row or row['total_evaluated'] == 0:
            logger.info(f"ℹ️ No results for {agent_name} | Project: {project_id}")
            return

        # Extract values
        relevancy_avg = float(row['relevancy_avg']) if row['relevancy_avg'] is not None else 0
        safety_avg = float(row['safety_avg']) if row['safety_avg'] is not None else 0
        coherence_avg = float(row['coherence_avg']) if row['coherence_avg'] is not None else 0
        helpfulness_avg = float(row['helpfulness_avg']) if row['helpfulness_avg'] is not None else 0
        toxicity_avg = float(row['toxicity_avg']) if row['toxicity_avg'] is not None else 0

        total_evaluated = row['total_evaluated']
        passed_count = row['passed_count']
        failed_count = total_evaluated - passed_count

        # Calculate overall score
        metric_values = [relevancy_avg, safety_avg, coherence_avg, helpfulness_avg, toxicity_avg]
        valid_metrics = [v for v in metric_values if v > 0]
        overall_score = sum(valid_metrics) / len(valid_metrics) if valid_metrics else 0

        # Save to averages table with both agent_name and project_id
        upsert_query = text("""
            INSERT INTO averages
                (id, agent_name, project_id, evaluation_date, 
                 relevancy_avg, safety_avg, coherence_avg, helpfulness_avg, toxicity_avg,
                 total_evaluated, passed_count, failed_count, overall_score, created_at)
            VALUES
                (:id, :agent_name, :project_id, CURRENT_DATE,
                 :relevancy_avg, :safety_avg, :coherence_avg, :helpfulness_avg, :toxicity_avg,
                 :total_evaluated, :passed_count, :failed_count, :overall_score, NOW())
            ON CONFLICT (agent_name, project_id, evaluation_date)
            DO UPDATE SET
                relevancy_avg = EXCLUDED.relevancy_avg,
                safety_avg = EXCLUDED.safety_avg,
                coherence_avg = EXCLUDED.coherence_avg,
                helpfulness_avg = EXCLUDED.helpfulness_avg,
                toxicity_avg = EXCLUDED.toxicity_avg,
                total_evaluated = EXCLUDED.total_evaluated,
                passed_count = EXCLUDED.passed_count,
                failed_count = EXCLUDED.failed_count,
                overall_score = EXCLUDED.overall_score,
                updated_at = NOW()
        """)

        await session.execute(upsert_query, {
            "id": str(uuid4()),
            "agent_name": agent_name,
            "project_id": project_id,
            "relevancy_avg": relevancy_avg,
            "safety_avg": safety_avg,
            "coherence_avg": coherence_avg,
            "helpfulness_avg": helpfulness_avg,
            "toxicity_avg": toxicity_avg,
            "total_evaluated": total_evaluated,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "overall_score": overall_score
        })
        await session.commit()

        # Log summary
        logger.info(f"\n📊 AVERAGES SAVED: {agent_name} | Project: {project_id}")
        logger.info(f"   Total: {total_evaluated} | Passed: {passed_count} | Failed: {failed_count}")
        logger.info(f"   Overall Score: {overall_score:.2f}")
        logger.info(f"   Relevancy: {relevancy_avg:.2f} | Safety: {safety_avg:.2f} | Coherence: {coherence_avg:.2f} | Helpfulness: {helpfulness_avg:.2f} | Toxicity: {toxicity_avg:.2f}")

# =====================================================
# MAIN EVALUATION LOGIC
# =====================================================

async def evaluate_agent(agent_name: str):
    """
    Evaluate a specific agent by name
    - Filters observations by agent_name
    - Auto-detects project_id
    - Stores both agent_name and project_id
    - Saves averages ONLY for projects (NO NULL)
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"  EVALUATING AGENT: {agent_name}")
    logger.info(f"{'='*60}")

    # 1. Build metrics from metric_master
    logger.info("📊 Building metrics from metric_master...")
    metrics = await build_metrics_from_master()

    if not metrics:
        logger.error("❌ No metrics available in metric_master")
        return

    logger.info(f"✅ Found {len(metrics)} metrics: {[m[0] for m in metrics]}")

    # 2. Get unevaluated observations for this agent (with project_id)
    logger.info(f"🔍 Filtering observations by agent: '{agent_name}' AND evaluated = false...")
    observations = await get_unevaluated_observations(agent_name, limit=100)

    if not observations:
        logger.info(f"ℹ️ No unevaluated observations found for agent: '{agent_name}'")
        return

    logger.info(f"✅ Found {len(observations)} unevaluated observations for agent: {agent_name}")

    # 3. Evaluate each observation
    total_evaluated = 0
    failed_evaluations = 0
    project_observations = {}

    for idx, obs in enumerate(observations, 1):
        observation_id = str(obs['id'])
        trace_id = str(obs['trace_id']) if obs.get('trace_id') else None
        project_id = str(obs['project_id']) if obs.get('project_id') else None
        agent_input = obs['input']
        agent_output = obs['output']

        # Skip if no project_id
        if not project_id:
            logger.warning(f"   ⚠️ Observation {observation_id} has no project_id, skipping...")
            continue

        # Group observations by project
        if project_id not in project_observations:
            project_observations[project_id] = []
        project_observations[project_id].append(obs)

        logger.info(f"\n📝 Observation {idx}/{len(observations)}")
        logger.info(f"   ID: {observation_id}")
        logger.info(f"   Agent: {agent_name}")
        logger.info(f"   Project: {project_id}")

        try:
            # Evaluate with all metrics
            results = await evaluate_observation(
                agent_input=agent_input,
                agent_output=agent_output,
                metrics=metrics
            )

            # Log results
            logger.info("   📊 Results:")
            all_passed = True
            for metric_name, metric_result in results.items():
                status = "✅ PASS" if metric_result['passed'] else "❌ FAIL"
                if not metric_result['passed']:
                    all_passed = False
                logger.info(f"      {metric_name:15s} → {metric_result['score']:.2f} (threshold: {metric_result['threshold']}) {status}")

            logger.info(f"   Overall: {'✅ ALL PASSED' if all_passed else '❌ SOME FAILED'}")

            # Save results with both agent_name and project_id
            await save_evaluation_results(
                observation_id=observation_id,
                trace_id=trace_id,
                agent_name=agent_name,
                project_id=project_id,
                results=results
            )

            # Mark observation as evaluated
            await mark_observation_evaluated(observation_id)
            total_evaluated += 1

        except Exception as e:
            logger.error(f"   ❌ Failed for {observation_id}: {e}")
            failed_evaluations += 1

    # 4. Calculate and save averages for EACH project (NO NULL rows)
    if total_evaluated > 0:
        for project_id, obs_list in project_observations.items():
            if obs_list:
                await calculate_and_save_averages(agent_name, project_id)

    # 5. Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"  EVALUATION SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"  Agent: {agent_name}")
    logger.info(f"  Total Observations: {len(observations)}")
    logger.info(f"  Successfully Evaluated: {total_evaluated}")
    logger.info(f"  Failed: {failed_evaluations}")
    logger.info(f"  Projects: {list(project_observations.keys()) if project_observations else 'None'}")
    logger.info(f"{'='*60}\n")

# =====================================================
# COMMAND LINE INTERFACE
# =====================================================

async def main():
    """
    Main function - only ask for agent name
    """
    print("\n" + "="*60)
    print("   DYNAMIC AGENT EVALUATION FRAMEWORK")
    print("="*60)

    # ONLY ask for agent name
    agent_name = input("\n🔍 Enter agent name to evaluate (e.g., rca_agent, decision_agent): ").strip()

    if not agent_name:
        print("❌ Agent name cannot be empty!")
        return

    print(f"\n✅ Evaluating agent: {agent_name}")
    print(f"ℹ️ Filter: name = '{agent_name}' AND evaluated = false")
    print(f"ℹ️ Project ID will be auto-detected from traces table\n")

    # Evaluate the agent
    await evaluate_agent(agent_name)

    print("\n✅ Evaluation complete!")

# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Evaluation cancelled by user")
    except Exception as e:
        logger.error(f"❌ Error: {e}")