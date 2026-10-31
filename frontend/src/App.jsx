import { Navigate, Route, Routes } from 'react-router-dom'
import './App.css'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import WorkspaceLayout from './components/WorkspaceLayout.jsx'
import CameraPic from './pages/camerapic.jsx'
import Demo from './pages/demo.jsx'
import Home from './pages/home.jsx'
import Phone from './pages/phone.jsx'
import SessionModel from './pages/session/SessionModel.jsx'
import SessionOverview from './pages/session/SessionOverview.jsx'
import SessionProcess from './pages/session/SessionProcess.jsx'
import SessionUploads from './pages/session/SessionUploads.jsx'

function Rendering3D() {
  return <h1>3D Rendering Page</h1>
}

function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/demo" element={<Demo />} />
        <Route path="/phone/:token" element={<Phone />} />
        {/* The backend returns phone_url as PUBLIC_BASE_URL/m/{pair_token}.
            Mounting the same page at /m/:token keeps that returned URL working
            while preserving the existing /phone/:token link. */}
        <Route path="/m/:token" element={<Phone />} />
        <Route path="/camerapic" element={<CameraPic />} />
        <Route path="/_3Drendering" element={<Rendering3D />} />

        <Route path="/session/:sessionId" element={<WorkspaceLayout />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<SessionOverview />} />
          <Route path="uploads" element={<SessionUploads />} />
          <Route path="process" element={<SessionProcess />} />
          <Route path="model" element={<SessionModel />} />
        </Route>
      </Routes>
    </ErrorBoundary>
  )
}

export default App
