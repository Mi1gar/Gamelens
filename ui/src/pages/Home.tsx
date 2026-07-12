import { useEffect } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { useGamesStore } from "../store/games";
import rdr2Card from "../assets/rdr2.png";
import metroCard from "../assets/metro.png";
import gta5Card from "../assets/gta5.png";
import rdr2Banner from "../assets/rdr2_banner.png";
import metroBanner from "../assets/metro2033_banner.png";
import gta5Banner from "../assets/gtav_banner.png";

const CARD_IMAGES: Record<string, string> = {
  rdr2: rdr2Card,
  metro_2033: metroCard,
  gta5: gta5Card,
};

const HERO_GAME = "rdr2";

export default function Home() {
  const navigate = useNavigate();
  const { games, loadGames, launchGame } = useGamesStore();

  useEffect(() => {
    loadGames();
  }, [loadGames]);

  const heroGame = games.find((g) => g.id === HERO_GAME);

  return (
    <div className="space-y-8">
      {/* TopBar */}
      <header className="flex justify-between items-center">
        <div className="relative w-96">
          <input
            type="text"
            placeholder="Oyun, paket veya özellik ara..."
            className="w-full bg-secondary/30 border border-white/10 rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary transition-all"
          />
        </div>
        <div className="flex items-center space-x-4">
          <div className="w-8 h-8 rounded-full bg-secondary" />
          <span className="font-medium text-sm">
            Doruk{" "}
            <span className="text-primary text-[10px] ml-1 bg-primary/10 px-1 py-0.5 rounded">
              PRO
            </span>
          </span>
        </div>
      </header>

      {/* Hero */}
      <div className="relative w-full h-[400px] rounded-2xl overflow-hidden group">
        <div className="absolute inset-0 bg-gradient-to-r from-black/80 via-black/40 to-transparent z-10" />
        <img
          src={rdr2Banner}
          className="absolute inset-0 w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
          alt="RDR 2"
        />
        <div className="absolute bottom-12 left-12 z-20 max-w-md">
          <div className="bg-primary/20 text-primary text-[10px] font-bold px-2 py-1 rounded mb-4 inline-block">
            ÖNERİLEN
          </div>
          <h2 className="text-4xl font-black text-white mb-2 tracking-tight">
            RED DEAD
            <br />
            REDEMPTION II
          </h2>
          <p className="text-xl font-bold text-white mb-2">Artık Türkçe!</p>
          <p className="text-sm text-gray-300 mb-6 line-clamp-2">
            Altyazıları anında çevir, hikayenin her anını kaçırma. Gelişmiş OCR
            ve YOLO motoru ile kesintisiz deneyim.
          </p>
          <div className="flex space-x-3">
            <button
              onClick={() => {
                if (heroGame) {
                  launchGame(heroGame.id);
                } else {
                  navigate(`/game/${HERO_GAME}`);
                }
              }}
              className="bg-primary text-primary-foreground font-bold px-6 py-2 rounded-lg hover:bg-primary/90 transition-colors"
            >
              Hemen Oyna
            </button>
            <button
              onClick={() => navigate(`/game/${HERO_GAME}`)}
              className="bg-white/10 text-white font-bold px-6 py-2 rounded-lg hover:bg-white/20 transition-colors backdrop-blur-sm border border-white/10"
            >
              Detaylar
            </button>
          </div>
        </div>
      </div>

      {/* Recent Games */}
      <div>
        <div className="flex justify-between items-end mb-4">
          <h3 className="text-lg font-bold flex items-center border-l-4 border-primary pl-3">
            Desteklenen Oyunlar
          </h3>
          <button
            onClick={() => navigate("/library")}
            className="text-sm text-muted-foreground hover:text-primary transition-colors"
          >
            Tümünü Gör {" >"}
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {games.slice(0, 4).map((game) => (
            <motion.div
              key={game.id}
              whileHover={{ scale: 1.02, y: -2 }}
              onClick={() => navigate(`/game/${game.id}`)}
              className="bg-secondary/20 rounded-xl overflow-hidden border border-white/5 cursor-pointer group hover:border-primary/30 transition-colors aspect-[9/16] flex flex-col"
            >
              <div className="flex-1 relative overflow-hidden">
                <img
                  src={CARD_IMAGES[game.id] ?? rdr2Card}
                  className="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  alt={game.name}
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent z-10" />
              </div>
              <div className="p-3 shrink-0">
                <h4 className="font-bold text-sm mb-1">{game.name}</h4>
                <p className="text-xs text-muted-foreground">
                  {Object.keys(game.capabilities).filter((k) => game.capabilities[k]).join(", ")}
                </p>
              </div>
            </motion.div>
          ))}
          {games.length === 0 &&
            [1, 2, 3, 4].map((idx) => (
              <div
                key={idx}
                className="bg-secondary/20 rounded-xl overflow-hidden border border-white/5 animate-pulse aspect-[9/16] flex flex-col"
              >
                <div className="flex-1 bg-secondary/50" />
                <div className="p-3 space-y-2">
                  <div className="h-4 bg-secondary/50 rounded w-3/4" />
                  <div className="h-3 bg-secondary/30 rounded w-1/2" />
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
