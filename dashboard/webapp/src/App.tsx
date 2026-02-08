import { Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import RunPage from './pages/RunPage';
import Layout from './components/Layout';

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/runs/:runId" element={<RunPage />} />
      </Routes>
    </Layout>
  );
}

export default App;
