import { useEffect } from "react";
import { motion } from "framer-motion";
import { Search, Filter, Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useGamesStore } from "../store/games";
import rdr2Card from "../assets/rdr2.png";
import metroCard from "../assets/metro.png";
import gta5Card from "../assets/gta5.png";

const CARD_IMAGES: Record<string, string> = {
  rdr2: rdr2Card,
  metro_2033: metroCard,
  gta5: gta5Card,
};

function gameImage(id: string): string {
  return CARD_IMAGES[id] ?? rdr2Card;
}

export default function Library() {
  const navigate = useNavigate();
  const { games, loading, error, loadGames } = useGamesStore();

  useEffect(() => {
    loadGames();
  }, [loadGames]);

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold mb-2 tracking-tight">
            Oyun Kütüphanesi
          </h2>
          <p className="text-muted-foreground">
            Desteklenen tüm oyunları ve çeviri durumlarını görüntüleyin.
          </p>
        </div>
        <div className="flex space-x-3">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="Kütüphanede ara..."
              className="bg-secondary/50 border border-white/10 rounded-lg pl-9 pr-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary transition-all w-64"
            />
          </div>
          <button className="bg-secondary/50 border border-white/10 rounded-lg p-2 hover:bg-secondary transition-colors">
            <Filter className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <span className="ml-3 text-muted-foreground">
            Oyunlar yükleniyor...
          </span>
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-center">
          <p className="text-red-400">
            Yüklenirken hata oluştu: {error}
          </p>
          <button
            onClick={() => loadGames()}
            className="mt-3 text-sm text-primary hover:underline"
          >
            Tekrar Dene
          </button>
        </div>
      )}

      {!loading && !error && games.length === 0 && (
        <div className="text-center py-20 text-muted-foreground">
          <p>Henüz desteklenen oyun bulunamadı.</p>
          <p className="text-sm mt-2">
            Python engine'in kurulu olduğundan emin olun.
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-6">
        {games.map((game, i) => (
          <motion.div
            key={game.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            whileHover={{ scale: 1.02, y: -4 }}
            onClick={() => navigate(`/game/${game.id}`)}
            className="bg-secondary/20 rounded-xl overflow-hidden border border-white/5 cursor-pointer group hover:border-primary/30 transition-all flex flex-col aspect-[9/16] shadow-lg hover:shadow-primary/5"
          >
            <div className="flex-1 relative overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent z-10" />
              <img
                src={gameImage(game.id)}
                className="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                alt={game.name}
              />
            </div>
            <div className="p-3 shrink-0">
              <h4 className="font-bold text-base leading-tight truncate">
                {game.name}
              </h4>
              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                {game.description}
              </p>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
