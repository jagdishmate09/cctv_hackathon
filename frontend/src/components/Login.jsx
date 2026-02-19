import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import '../styles/login.css';

function Login() {
    const navigate = useNavigate();
    const [showPassword, setShowPassword] = useState(false);
    const [formData, setFormData] = useState({
        email: '',
        password: ''
    });
    const [isLoading, setIsLoading] = useState(false);

    const handleInputChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: value
        }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        
        // Simulate API call
        setTimeout(() => {
            console.log('Login attempt:', formData);
            setIsLoading(false);
            // Navigate to dashboard after successful login
            navigate('/dashboard');
        }, 1000);
    };


    const togglePasswordVisibility = () => {
        setShowPassword(prev => !prev);
    };

    return (
        <div className="login-page-wrapper">
            <div className="login-container">
            <div className="login-wrapper">
                <div className="login-right">
                    <div className="login-form-container">
                        <div className="container-title">
                            <h1>DPA ONE</h1>
                        </div>
                        <form className="login-form" id="loginForm" onSubmit={handleSubmit}>
                            <div className="form-group">
                                <label htmlFor="email">Username</label>
                                <div className="input-wrapper">
                                    <svg className="input-icon" width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                        <path d="M10 10C12.7614 10 15 7.76142 15 5C15 2.23858 12.7614 0 10 0C7.23858 0 5 2.23858 5 5C5 7.76142 7.23858 10 10 10Z" fill="currentColor"/>
                                        <path d="M10 12.5C5.58172 12.5 2 15.5817 2 20H18C18 15.5817 14.4183 12.5 10 12.5Z" fill="currentColor"/>
                                    </svg>
                                    <input 
                                        type="text" 
                                        id="email" 
                                        name="email" 
                                        placeholder="Enter username" 
                                        required
                                        autoComplete="username"
                                        value={formData.email}
                                        onChange={handleInputChange}
                                    />
                                </div>
                            </div>
                            <div className="form-group">
                                <label htmlFor="password">Password</label>
                                <div className="input-wrapper">
                                    <svg className="input-icon" width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                        <path d="M15.8333 9.16667V5.83333C15.8333 3.53215 13.9681 1.66667 11.6667 1.66667H8.33333C6.03185 1.66667 4.16667 3.53215 4.16667 5.83333V9.16667M10 14.5833V16.25M5.83333 9.16667H14.1667C15.0871 9.16667 15.8333 9.91286 15.8333 10.8333V16.25C15.8333 17.1705 15.0871 17.9167 14.1667 17.9167H5.83333C4.91286 17.9167 4.16667 17.1705 4.16667 16.25V10.8333C4.16667 9.91286 4.91286 9.16667 5.83333 9.16667Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                    </svg>
                                    <input 
                                        type={showPassword ? "text" : "password"} 
                                        id="password" 
                                        name="password" 
                                        placeholder="Enter your password" 
                                        required
                                        autoComplete="current-password"
                                        value={formData.password}
                                        onChange={handleInputChange}
                                    />
                                    <button 
                                        type="button" 
                                        className="password-toggle" 
                                        id="passwordToggle" 
                                        aria-label="Toggle password visibility"
                                        onClick={togglePasswordVisibility}
                                    >
                                        <svg className="eye-icon" width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                            <path d="M10 4.16667C13.3333 4.16667 15.8333 7.5 15.8333 7.5C15.8333 7.5 13.3333 10.8333 10 10.8333M10 4.16667C6.66667 4.16667 4.16667 7.5 4.16667 7.5C4.16667 7.5 6.66667 10.8333 10 10.8333M10 4.16667V2.5M10 10.8333V12.5M4.16667 7.5H2.5M15.8333 7.5H17.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                            <path d="M2.5 2.5L17.5 17.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                                        </svg>
                                    </button>
                                </div>
                            </div>
                            <button 
                                type="submit" 
                                className={`submit-btn ${isLoading ? 'loading' : ''}`}
                                disabled={isLoading}
                            >
                                <span>Sign In</span>
                                <svg className="arrow-icon" width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M7.5 15L12.5 10L7.5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                                </svg>
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
        </div>
    );
}

export default Login;

