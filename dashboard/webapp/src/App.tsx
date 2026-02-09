import { Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import RunPage from './pages/RunPage';
import PromptsPage from './pages/PromptsPage';
import SecurityPage from './pages/SecurityPage';
import Layout from './components/Layout';

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/runs/:runId" element={<RunPage />} />
        <Route path="/prompts" element={<PromptsPage />} />
        <Route path="/security" element={<SecurityPage />} />
      </Routes>
    </Layout>
  );
}

export default App;
