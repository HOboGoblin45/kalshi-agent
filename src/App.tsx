import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ToastProvider } from "./components/Toast";
import Layout from "./components/Layout";
import Markets from "./pages/Markets";
import BotIntelligence from "./pages/BotIntelligence";
import Positions from "./pages/Positions";
import Alerts from "./pages/Alerts";
import MarketDetail from "./pages/MarketDetail";
import Profile from "./pages/Profile";

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Markets />} />
            <Route path="/bot" element={<BotIntelligence />} />
            <Route path="/positions" element={<Positions />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/market/:id" element={<MarketDetail />} />
            <Route path="/profile" element={<Profile />} />
          </Route>
        </Routes>
      </ToastProvider>
    </BrowserRouter>
  );
}
