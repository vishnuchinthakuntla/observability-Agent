import React, { useState } from 'react'
import mainImg from '../assets/obserbulity.png'
import './login.css'
import Sidebar from '../components/Sidebar/sidebar'
import AppRoutes from '../routes/AppRoutes'
import TopBar from '../layout/TopBar'
import '../layout/dashboard.css'


interface LoginProps { }

const Login: React.FC<LoginProps> = () => {
    const [username, setUsername] = useState<string>('')
    const [password, setPassword] = useState<string>('')
    const [show, setShow] = useState<boolean>(false)
    const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false)
    const [error, setError] = useState<string | null>(null)
    const [active, setActive] = useState<'dashboard' | 'obserbulity'>('dashboard')

    const canSubmit: boolean = username.trim() !== '' && password.trim() !== ''

    const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault()
        if (!canSubmit) return
        // simple static auth as requested: username=admin password=admin
        if (username === 'admin' && password === 'admin') {
            setError(null)
            setIsAuthenticated(true)
        } else {
            setError('Invalid credentials — use username: admin and password: admin')
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
                    <div className="form-card">
                        <h2 className="form-title">Login</h2>
                        <form onSubmit={handleSubmit}>
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
                                disabled={!canSubmit}
                            >
                                Login
                            </button>
                            {error && <div className="error">{error}</div>}
                        </form>

                        <div className="links-row">
                            <p>
                                Need an account? <a href="#">Register</a> · <a href="#">Forgot Password?</a>
                            </p>
                        </div>

                        <div className="footer">
                            Powered by: <a href="#" target="_blank" rel="noreferrer">Covalense Global</a>
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
