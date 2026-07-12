import { Routes, Route, useLocation } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import AppShell from "./components/layout/AppShell";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Library from "./pages/Library";
import GameDetail from "./pages/GameDetail";
import Settings from "./pages/Settings";

function App() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<AppShell />}>
          <Route index element={<Home />} />
          <Route path="library" element={<Library />} />
          <Route path="game/:id" element={<GameDetail />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </AnimatePresence>
  );
}

export default App;
