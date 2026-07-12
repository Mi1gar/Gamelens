import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Play,
  Square,
  Settings2,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { useGamesStore } from "../store/games";
import rdr2Card from "../assets/rdr2.png";
import metroCard from "../assets/metro.png";
import gta5Card from "../assets/gta5.png";
import rdr2Banner from "../assets/rdr2_banner.png";
import metroBanner from "../assets/metro2033_banner.png";
import gta5Banner from "../assets/gtav_banner.png";

const HERO_IMAGES: Record<string, string> = {
  rdr2: rdr2Banner,
  metro_2033: metroBanner,
  gta5: gta5Banner,
};

const CARD_IMAGES: Record<string, string> = {
  rdr2: rdr2Card,
  metro_2033: metroCard,
  gta5: gta5Card,
};

export default function GameDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { games, loadGames, launchGame, stopEngine, engineStatus, activeGame } =
    useGamesStore();
  const [monitorIdx, setMonitorIdx] = useState(1);

  useEffect(() => {
    loadGames();
  }, [loadGames]);

  const game = games.find((g) => g.id === id);

  const isThisGameRunning =
    engineStatus === "running" && activeGame === id;
  const isStarting =
    engineStatus === "starting" && activeGame === id;

  const handleLaunch = async () => {
    if (!id) return;
    await launchGame(id, monitorIdx);
  };

  const handleStop = async () => {
    await stopEngine();
  };

  if (!game) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <span className="ml-3 text-muted-foreground">Yükleniyor...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <button
        onClick={() => navigate(-1)}
        className="flex items-center text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="w-4 h-4 mr-2" /> Geri Dön
      </button>

      {/* Hero */}
      <div className="relative w-full h-[350px] rounded-2xl overflow-hidden group border border-white/10 shadow-2xl">
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-transparent z-10" />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/20 to-transparent z-10" />
        <img
          src={HERO_IMAGES[id!] ?? rdr2Banner}
          className="absolute inset-0 w-full h-full object-cover"
          alt={game.name}
        />

        <div className="absolute bottom-10 left-10 z-20 max-w-2xl">
          <div className="flex items-center space-x-3 mb-4">
            <span className="bg-primary/20 text-primary border border-primary/30 text-xs font-bold px-2 py-1 rounded">
              Destekleniyor
            </span>
            {isThisGameRunning && (
              <span className="bg-green-500/20 text-green-400 border border-green-500/30 text-xs px-2 py-1 rounded flex items-center">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400 mr-1.5 animate-pulse" />
                Çalışıyor
              </span>
            )}
          </div>
          <h1 className="text-5xl font-black text-white mb-4 tracking-tight">
            {game.name}
          </h1>
          <p className="text-lg text-gray-300 mb-8 leading-relaxed">
            {game.description}
          </p>

          <div className="flex items-center space-x-4">
            {isThisGameRunning ? (
              <button
                onClick={handleStop}
                className="flex items-center bg-red-600 text-white font-bold px-8 py-4 rounded-xl hover:bg-red-500 transition-all shadow-[0_0_20px_rgba(220,38,38,0.4)] hover:scale-105 active:scale-95"
              >
                <Square className="w-5 h-5 mr-3 fill-current" />
                Durdur
              </button>
            ) : (
              <button
                onClick={handleLaunch}
                disabled={isStarting}
                className="flex items-center bg-primary text-primary-foreground font-bold px-8 py-4 rounded-xl hover:bg-primary/90 transition-all shadow-[0_0_20px_rgba(204,255,0,0.4)] hover:scale-105 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
              >
                {isStarting ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-3 animate-spin" />
                    Başlatılıyor...
                  </>
                ) : (
                  <>
                    <Play className="w-5 h-5 mr-3 fill-current" />
                    Oyunu Başlat
                  </>
                )}
              </button>
            )}

            {/* Monitor selector */}
            <div className="flex items-center bg-secondary/80 backdrop-blur rounded-xl border border-white/10 px-4 py-2">
              <Settings2 className="w-4 h-4 mr-2 text-muted-foreground" />
              <select
                value={monitorIdx}
                onChange={(e) => setMonitorIdx(Number(e.target.value))}
                className="bg-transparent text-sm font-medium focus:outline-none"
              >
                <option value={1}>Monitör 1</option>
                <option value={2}>Monitör 2</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Info grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="col-span-2 bg-card rounded-2xl border border-white/5 p-8 shadow-xl"
        >
          <h3 className="text-xl font-bold mb-6">Çeviri Motoru</h3>

          <div className="flex items-center p-4 bg-secondary/30 rounded-xl border border-white/5 mb-6">
            <div className="w-12 h-12 bg-green-500/20 rounded-full flex items-center justify-center mr-4 shrink-0">
              <CheckCircle2 className="w-6 h-6 text-green-500" />
            </div>
            <div>
              <h4 className="font-bold">NLLB-200 AI Modeli Hazır</h4>
              <p className="text-sm text-muted-foreground">
                EN → TR, offline, GPU hızlandırmalı
              </p>
            </div>
          </div>

          <div className="space-y-3">
            <h4 className="font-semibold text-sm">Aktif Özellikler</h4>
            <ul className="space-y-2">
              {[
                "YOLO altyazı tespiti",
                "RapidOCR metin tanıma (GPU)",
                "NLLB-200 çeviri (35-60ms)",
                "Growing DB (oynadıkça öğrenir)",
                "HUD / watermark filtreleme",
              ].map((feat, i) => (
                <li key={i} className="flex items-center text-sm">
                  <div className="w-1.5 h-1.5 rounded-full bg-primary mr-3" />
                  {feat}
                </li>
              ))}
            </ul>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-card rounded-2xl border border-white/5 p-8 shadow-xl"
        >
          <h3 className="text-xl font-bold mb-6">Oyun Bilgisi</h3>
          <ul className="space-y-4">
            {Object.entries(game.capabilities).map(([key, val]) => (
              <li key={key} className="flex items-center">
                <div
                  className={`w-2 h-2 rounded-full mr-3 ${
                    val ? "bg-primary" : "bg-muted"
                  }`}
                />
                <span
                  className={
                    val ? "text-foreground" : "text-muted-foreground line-through"
                  }
                >
                  {key === "dialogue"
                    ? "Diyalog Çevirisi"
                    : key === "journal"
                      ? "Günlük Çevirisi"
                      : key === "notifications"
                        ? "Bildirim Çevirisi"
                        : key}
                </span>
              </li>
            ))}
          </ul>

          <div className="mt-6 pt-6 border-t border-white/5">
            <p className="text-xs text-muted-foreground">
              Overlay altyazının altında siyah şerit olarak görünür. Oyunun
              orijinal altyazısını kapatmaz.
            </p>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
