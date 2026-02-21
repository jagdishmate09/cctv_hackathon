import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import '../styles/login.css';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000';

function Login() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        const err = searchParams.get('error');
        if (err) {
            const messages = {
                no_code: 'Sign-in was cancelled or no authorization code was received.',
                server_config: 'Server SSO is not configured.',
                token_exchange: 'Sign-in failed during token exchange.',
                no_token: 'No access token received from Microsoft.',
            };
            setError(messages[err] || `Sign-in error: ${err}`);
        }
    }, [searchParams]);

    const handleMicrosoftSignIn = () => {
        setIsLoading(true);
        window.location.href = `${API_BASE}/auth/microsoft`;
    };

    return (
        <div className="login-page-wrapper">
            <div className="login-container">
                <div className="login-wrapper">
                    <div className="login-right">
                        <div className="login-form-container">
                            <div className="container-title">
                                <h1>IntelliSpace AI</h1>
                            </div>
                            <div className="login-form sso-only">
                                <p className="login-subtitle">Sign in with your Microsoft account</p>
                                {error && (
                                    <div className="login-error" role="alert">
                                        {error}
                                    </div>
                                )}
                                <button
                                    type="button"
                                    className="submit-btn microsoft-sso-btn"
                                    onClick={handleMicrosoftSignIn}
                                    disabled={isLoading}
                                >
                                    {isLoading ? (
                                        <span>Redirecting…</span>
                                    ) : (
                                        <>
                                            <svg className="microsoft-icon" width="20" height="20" viewBox="0 0 21 21" fill="none">
                                                <rect x="1" y="1" width="9" height="9" fill="#F25022"/>
                                                <rect x="11" y="1" width="9" height="9" fill="#7FBA00"/>
                                                <rect x="1" y="11" width="9" height="9" fill="#00A4EF"/>
                                                <rect x="11" y="11" width="9" height="9" fill="#FFB900"/>
                                            </svg>
                                            <span>Sign in with Microsoft</span>
                                        </>
                                    )}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Login;
