import { Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import RunPage from './pages/RunPage';
import PromptsPage from './pages/PromptsPage';
import Layout from './components/Layout';

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/runs/:runId" element={<RunPage />} />
        <Route path="/prompts" element={<PromptsPage />} />
      </Routes>
    </Layout>
  );
}

export default App;
