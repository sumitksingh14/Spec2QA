import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import StoryInput from './pages/StoryInput';
import StoryDetails from './pages/StoryDetails';

function App() {
  return (
    <Router>
      <div className="app-container">
        <nav className="navbar">
          <div className="nav-brand">
            <Link to="/" style={{ textDecoration: 'none', color: 'inherit' }}>
            Spec2QA
            </Link>
          </div>
          <div>
            <Link to="/new-story" className="btn btn-primary">
              + New Story
            </Link>
          </div>
        </nav>
        
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/new-story" element={<StoryInput />} />
            <Route path="/story/:id" element={<StoryDetails />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
