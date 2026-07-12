import { motion } from "framer-motion";
import { Monitor, Globe, Cpu } from "lucide-react";

export default function Settings() {
  type SettingItem =
    | { name: string; type: "toggle"; value: boolean }
    | { name: string; type: "select"; options: string[] }
    | { name: string; type: "slider"; value: number };

  const settingsSections: {
    title: string;
    icon: typeof Monitor;
    items: SettingItem[];
  }[] = [
    {
      title: "Uygulama",
      icon: Monitor,
      items: [
        { name: "Sistem başlangıcında çalıştır", type: "toggle", value: false },
        { name: "Donanım hızlandırmayı etkinleştir", type: "toggle", value: true },
        { name: "Görünüm Teması", type: "select", options: ["Koyu Tema", "Açık Tema", "Sistem Varsayılanı"] }
      ]
    },
    {
      title: "Çeviri Motoru",
      icon: Globe,
      items: [
        { name: "Yapay Zeka Motoru", type: "select", options: ["GameLens NMT (Offline)", "DeepL API (Pro)", "Google Translate"] },
        { name: "Çeviri Gecikme Modu", type: "select", options: ["Hız Odaklı (Sıfır Gecikme)", "Kalite Odaklı (Bağlamsal Çeviri)"] },
        { name: "Çevrimdışı Paketleri Otomatik Güncelle", type: "toggle", value: true }
      ]
    },
    {
      title: "Oyun İçi Overlay",
      icon: Cpu,
      items: [
        { name: "Altyazı Boyutu", type: "slider", value: 16 },
        { name: "Arka Plan Opaklığı", type: "slider", value: 80 },
        { name: "Görüntü İşleme (OCR) Hassasiyeti", type: "slider", value: 90 },
      ]
    }
  ];

  return (
    <div className="max-w-4xl space-y-8">
      <div>
        <h2 className="text-3xl font-bold mb-2 tracking-tight">Ayarlar</h2>
        <p className="text-muted-foreground">Uygulama davranışını ve çeviri motoru tercihlerini yapılandırın.</p>
      </div>

      <div className="flex flex-col lg:flex-row gap-8">
        {/* Left Side Navigation (Optional, skipped for brevity, just stacking cards) */}
        
        <div className="flex-1 space-y-6">
          {settingsSections.map((section, idx) => (
            <motion.div 
              key={idx}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.1 }}
              className="bg-card rounded-2xl border border-white/5 p-6 shadow-xl"
            >
              <h3 className="text-lg font-bold mb-6 flex items-center border-b border-white/5 pb-4">
                <section.icon className="w-5 h-5 mr-3 text-primary" /> {section.title}
              </h3>
              
              <div className="space-y-6">
                {section.items.map((item, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <span className="text-sm font-medium">{item.name}</span>
                    
                    {item.type === "toggle" && (
                      <div className={`w-12 h-6 rounded-full p-1 cursor-pointer transition-colors ${item.value ? 'bg-primary' : 'bg-secondary'}`}>
                        <div className={`w-4 h-4 bg-black rounded-full transition-transform ${item.value ? 'translate-x-6' : 'translate-x-0 bg-white/70'}`} />
                      </div>
                    )}
                    
                    {item.type === "select" && item.options && (
                      <select className="bg-secondary border border-white/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary appearance-none w-48 cursor-pointer">
                        {item.options.map((opt, oi) => <option key={oi}>{opt}</option>)}
                      </select>
                    )}
                    
                    {item.type === "slider" && (
                      <div className="flex items-center w-48">
                        <input type="range" min="0" max="100" defaultValue={item.value as number} className="w-full accent-primary" />
                        <span className="text-xs text-muted-foreground ml-3 w-6">{item.value}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
