import { Routes, Route } from 'react-router-dom'
import './App.css'
import Home from './pages/home.jsx'
import CameraPic from './pages/camerapic.jsx'

function Rendering3D() {
  return <h1>3D Rendering Page</h1>
}

function App() {

  return (
    <>
      <Routes>
        <Route path="/" element={<Home />}/>
        <Route path="/camerapic" element={<CameraPic />}/>
        <Route path="/_3Drendering" element={<Rendering3D />}/>
      </Routes>
    </>
  )
}

export default App
