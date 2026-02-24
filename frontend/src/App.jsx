import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './components/Login';
import Dashboard from './components/Dashboard';
import './App.css';

// SSO disabled – direct entry; re-enable by uncommenting the check below and restoring "/" → "/login"
function RequireAuth({ children }) {
  // const location = useLocation();
  // const hasToken = typeof window !== 'undefined' && sessionStorage.getItem('sso_token');
  // const hasTokenInUrl = typeof window !== 'undefined' && new URLSearchParams(location.search).get('token');
  // if (!hasToken && !hasTokenInUrl) return <Navigate to="/login" replace />;
  return children;
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Router>
  );
}

export default App;
