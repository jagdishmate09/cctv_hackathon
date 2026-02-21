import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Login from './components/Login';
import Dashboard from './components/Dashboard';
import './App.css';

function RequireAuth({ children }) {
  const location = useLocation();
  const hasToken = typeof window !== 'undefined' && sessionStorage.getItem('sso_token');
  const hasTokenInUrl = typeof window !== 'undefined' && new URLSearchParams(location.search).get('token');
  if (!hasToken && !hasTokenInUrl) return <Navigate to="/login" replace />;
  return children;
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
        <Route path="/" element={<Navigate to="/login" replace />} />
      </Routes>
    </Router>
  );
}

export default App;
