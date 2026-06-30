ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE;
-- 1. Add the missing project_id column and foreign key link


ALTER TABLE users ADD COLUMN project_id VARCHAR(36);
ALTER TABLE users ADD CONSTRAINT fk_user_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

-- 2. Replace the old string UUID with an auto-incrementing Integer ID
ALTER TABLE users DROP COLUMN id;
ALTER TABLE users ADD COLUMN id SERIAL PRIMARY KEY;


