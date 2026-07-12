import { NavLink, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Home, Library, Gamepad2, PackageSearch, Bell, Settings } from "lucide-react";

const navItems = [
  { name: "Ana Sayfa", icon: Home, path: "/" },
  { name: "Kütüphane", icon: Library, path: "/library" },
  { name: "Desteklenen Oyunlar", icon: Gamepad2, path: "/supported" },
  { name: "Çeviri Paketleri", icon: PackageSearch, path: "/packs" },
  { name: "Güncellemeler", icon: Bell, path: "/updates", badge: 2 },
  { name: "Ayarlar", icon: Settings, path: "/settings" },
];

export default function Sidebar() {
  const navigate = useNavigate();

  return (
    <div className="w-64 h-screen bg-card border-r flex flex-col pt-6 pb-6 shadow-xl z-10">
      {/* Logo */}
      <div className="flex items-center px-6 mb-12">
        <div className="w-8 h-8 rounded bg-primary flex items-center justify-center mr-3">
          <Gamepad2 className="w-5 h-5 text-primary-foreground" />
        </div>
        <div>
          <h1 className="font-bold text-lg leading-tight tracking-tight">GAMELENS</h1>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Play Without Limits</p>
        </div>
      </div>

      {/* Nav Links */}
      <nav className="flex-1 px-4 space-y-2">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `relative flex items-center px-4 py-3 rounded-lg transition-colors group ${
                isActive ? "text-primary" : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.div
                    layoutId="active-nav"
                    className="absolute inset-0 bg-primary/10 rounded-lg border border-primary/20"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  />
                )}
                {isActive && (
                  <motion.div
                    layoutId="active-indicator"
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-primary rounded-r-full"
                  />
                )}
                <item.icon className={`w-5 h-5 mr-4 relative z-10 ${isActive ? "text-primary" : ""}`} />
                <span className="font-medium text-sm relative z-10">{item.name}</span>
                
                {item.badge && (
                  <div className="ml-auto relative z-10 bg-primary text-primary-foreground text-[10px] font-bold w-5 h-5 flex items-center justify-center rounded-full">
                    {item.badge}
                  </div>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Engine Status Placeholder */}
      <div className="px-6 mt-auto">
        <div className="bg-secondary/50 p-4 rounded-xl border border-white/5">
          <p className="text-xs text-muted-foreground mb-1">Çeviri Motoru</p>
          <div className="flex items-center">
            <div className="w-2 h-2 rounded-full bg-green-500 mr-2 shadow-[0_0_8px_rgba(34,197,94,0.6)]" />
            <span className="text-sm font-medium text-green-500">Aktif</span>
          </div>
          <p className="text-[10px] text-muted-foreground mt-2">YOLO • OCR • NMT</p>
        </div>
        <button
          onClick={() => navigate("/library")}
          className="w-full mt-4 bg-primary text-primary-foreground hover:bg-primary/90 font-bold py-3 rounded-xl transition-all shadow-[0_0_15px_rgba(204,255,0,0.3)] hover:shadow-[0_0_25px_rgba(204,255,0,0.5)] flex items-center justify-center"
        >
          <Gamepad2 className="w-4 h-4 mr-2" />
          Oyunu Başlat
        </button>
      </div>
    </div>
  );
}
