import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { NavBar } from './components/NavBar.tsx'
import { ReviewPage } from './pages/ReviewPage.tsx'
import { ResultsPage } from './pages/ResultsPage.tsx'
import { HistoryPage } from './pages/HistoryPage.tsx'
import './app.css'

export default function App() {
  return (
    <BrowserRouter>
      <NavBar />
      <Routes>
        <Route path="/" element={<ReviewPage />} />
        <Route path="/results/:runId" element={<ResultsPage />} />
        <Route path="/history" element={<HistoryPage />} />
      </Routes>
    </BrowserRouter>
  )
}
