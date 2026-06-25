import React, { useEffect, useState } from 'react'
import mainImg from '../assets/obserbulity.png'
import './login.css'
import Sidebar from '../components/Sidebar/sidebar'
import AppRoutes from '../routes/AppRoutes'
import TopBar from '../layout/TopBar'
import '../layout/dashboard.css'


interface LoginProps { }

const Login: React.FC<LoginProps> = () => {
    const [mode, setMode] = useState<'login' | 'register'>('login')
    const [username, setUsername] = useState<string>('')
    const [email, setEmail] = useState<string>('')
    const [password, setPassword] = useState<string>('')
    const [show, setShow] = useState<boolean>(false)
    const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false)
    const [error, setError] = useState<string | null>(null)
    const [statusMessage, setStatusMessage] = useState<string | null>(null)
    const [loading, setLoading] = useState<boolean>(false)

    const canSubmit: boolean = username.trim() !== '' && password.trim() !== '' && (mode === 'login' || email.trim() !== '')

    useEffect(() => {
        const token = localStorage.getItem('authToken')
        if (token) {
            setIsAuthenticated(true)
        }
    }, [])

    const apiBase = String(import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '')

    const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault()
        if (!canSubmit) return

        setLoading(true)
        setError(null)
        setStatusMessage(null)

        try {
            const endpoint = mode === 'register' ? '/custom-api/v1/register' : '/custom-api/v1/login'
            const url = apiBase ? `${apiBase}${endpoint}` : endpoint
            const payload = mode === 'register'
                ? { username, email, password }
                : { username, password }

            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            })

            const result = await response.json()

            if (!response.ok) {
                throw new Error(result.message || result.error || 'Authentication failed')
            }

            if (mode === 'register') {
                setMode('login')
                setStatusMessage('Registration successful. Please login.')
                setPassword('')
                setEmail('')
            } else {
                const token = result.token || result.access_token || result.data?.token || ''
                if (token) {
                    localStorage.setItem('authToken', token)
                }
                setIsAuthenticated(true)
            }
        } catch (err: any) {
            setError(err.message || 'Unable to authenticate. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    if (isAuthenticated) {
        return (
            <div className="shell">
                <Sidebar />

                <div className="main">
                    <TopBar />

                    <div className="content">
                        <AppRoutes />
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="login-page">
            <div className="login-card">
                <div className="left-panel">
                    <div className="form-card-container">
                        <div className="form-card">
                            <div className="card-header">
                                <h2 className="form-title">{mode === 'login' ? 'Login' : 'Register'}</h2>
                                <p className="form-subtitle">{mode === 'login' ? 'Welcome back' : 'Create new account'}</p>
                            </div>

                            <form onSubmit={handleSubmit} className="auth-form">
                                <label className="input-group">
                                    <svg
                                        className="input-icon"
                                        viewBox="0 0 24 24"
                                        width="18"
                                        height="18"
                                        fill="none"
                                        stroke="currentColor"
                                        strokeWidth="1.5"
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                    >
                                        <path d="M3 8v8a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8" />
                                        <rect x="3" y="3" width="18" height="4" rx="2" ry="2" />
                                    </svg>
                                    <input
                                        className="input"
                                        type="text"
                                        placeholder="Username"
                                        value={username}
                                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                            setUsername(e.target.value)
                                        }
                                        required
                                    />
                                </label>

                                {mode === 'register' && (
                                    <label className="input-group">
                                        <svg
                                            className="input-icon"
                                            viewBox="0 0 24 24"
                                            width="18"
                                            height="18"
                                            fill="none"
                                            stroke="currentColor"
                                            strokeWidth="1.5"
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                        >
                                            <path d="M21 10v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7" />
                                            <path d="M7 10V7a5 5 0 0 1 10 0v3" />
                                            <path d="M12 14a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" />
                                        </svg>
                                        <input
                                            className="input"
                                            type="email"
                                            placeholder="Email"
                                            value={email}
                                            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                                setEmail(e.target.value)
                                            }
                                            required={mode === 'register'}
                                        />
                                    </label>
                                )}

                                <label className="input-group">
                                    <svg
                                        className="input-icon"
                                        viewBox="0 0 24 24"
                                        width="18"
                                        height="18"
                                        fill="none"
                                        stroke="currentColor"
                                        strokeWidth="1.5"
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                    >
                                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                                        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                                    </svg>
                                    <input
                                        className="input"
                                        type={show ? 'text' : 'password'}
                                        placeholder="Password"
                                        value={password}
                                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                            setPassword(e.target.value)
                                        }
                                        required
                                    />
                                    <button
                                        type="button"
                                        className="eye-button"
                                        onClick={() => setShow((s) => !s)}
                                        aria-label="Toggle password visibility"
                                    >
                                        {show ? (
                                            <svg
                                                width="18"
                                                height="18"
                                                viewBox="0 0 24 24"
                                                fill="none"
                                                stroke="currentColor"
                                                strokeWidth="1.5"
                                            >
                                                <path d="M17.94 17.94A10.95 10.95 0 0 1 12 20c-5.05 0-9.32-3.02-11-7 1.01-2.12 2.9-3.86 5.12-4.89" />
                                                <path d="M1 1l22 22" />
                                            </svg>
                                        ) : (
                                            <svg
                                                width="18"
                                                height="18"
                                                viewBox="0 0 24 24"
                                                fill="none"
                                                stroke="currentColor"
                                                strokeWidth="1.5"
                                            >
                                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z" />
                                                <circle cx="12" cy="12" r="3" />
                                            </svg>
                                        )}
                                    </button>
                                </label>

                                <button
                                    type="submit"
                                    className={`login-btn ${canSubmit ? 'enabled' : ''}`}
                                    disabled={!canSubmit || loading}
                                >
                                    {loading ? (mode === 'login' ? 'Logging in...' : 'Registering...') : mode === 'login' ? 'Login' : 'Register'}
                                </button>
                                {error && <div className="error">{error}</div>}
                                {statusMessage && <div className="success">{statusMessage}</div>}
                            </form>

                            <div className="card-footer">
                                <div className="links-row">
                                    <p>
                                        {mode === 'login' ? (
                                            <>Need an account? <button type="button" className="link-button" onClick={() => { setMode('register'); setError(null); setStatusMessage(null); }}>
                                                Register
                                            </button></>
                                        ) : (
                                            <>Already have an account? <button type="button" className="link-button" onClick={() => { setMode('login'); setError(null); setStatusMessage(null); }}>
                                                Login
                                            </button></>
                                        )}
                                        {' '}· <a href="#">Forgot Password?</a>
                                    </p>
                                </div>

                                <div className="footer">
                                    Powered by: <a href="#" target="_blank" rel="noreferrer">Covalense Global</a>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="right-panel">
                    <img src={mainImg} alt="Obserbulity" className="right-main-image" />
                </div>
            </div>
        </div>
    )
}

export default Login
