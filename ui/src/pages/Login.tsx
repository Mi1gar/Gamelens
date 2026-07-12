import { motion } from "framer-motion";
import { Gamepad2 } from "lucide-react";

export default function Login() {
  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      
      {/* Left Panel - Branding & Visuals */}
      <div className="relative hidden lg:flex flex-1 flex-col justify-between p-12 bg-black border-r border-white/10 overflow-hidden">
        {/* Animated Background */}
        <div className="absolute inset-0 z-0">
          <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1552820728-8b83bb6b773f?q=80&w=1000')] bg-cover bg-center opacity-30 mix-blend-screen filter blur-[2px]" />
          <div className="absolute inset-0 bg-gradient-to-tr from-purple-900/40 via-background to-background" />
          <div className="absolute inset-0 bg-gradient-to-t from-background via-transparent to-transparent" />
        </div>

        <div className="relative z-10 flex items-center">
          <div className="w-10 h-10 rounded bg-primary flex items-center justify-center mr-3">
            <Gamepad2 className="w-6 h-6 text-primary-foreground" />
          </div>
          <h1 className="font-bold text-3xl tracking-tight text-primary">GAMELENS</h1>
        </div>

        <div className="relative z-10 max-w-md">
          <h2 className="text-4xl font-bold mb-4 leading-tight">Play Without<br/>Language Limits</h2>
          <div className="space-y-6 mt-12">
            {[
              { title: "Anında Çeviri", desc: "Altyazıları gerçek zamanlı çevirir." },
              { title: "Desteklenen Oyunlar", desc: "1000+ oyunla uyumlu çalışır." },
              { title: "Yerel ve Güçlü", desc: "Verilerin güvende, işlemler tamamen yerel." }
            ].map((feature, i) => (
              <motion.div 
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.2 * i }}
                key={i} 
                className="flex items-start"
              >
                <div className="w-10 h-10 rounded-lg bg-secondary/50 flex items-center justify-center mr-4 border border-white/10 shrink-0">
                  <Gamepad2 className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <h3 className="font-bold">{feature.title}</h3>
                  <p className="text-sm text-gray-400">{feature.desc}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>

      {/* Right Panel - Form */}
      <div className="flex-1 flex flex-col items-center justify-center p-8 relative">
        <div className="absolute top-0 right-0 w-96 h-96 bg-primary/5 rounded-full blur-3xl pointer-events-none" />
        
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-md bg-card/50 backdrop-blur-xl p-8 rounded-2xl border border-white/5 shadow-2xl"
        >
          <div className="text-center mb-8">
            <h2 className="text-2xl font-bold mb-2">GameLens'e <span className="text-primary">Hoş Geldin</span></h2>
            <p className="text-sm text-muted-foreground">Oyunların dilini aş, hikayeye odaklan.</p>
          </div>

          <div className="flex border-b border-white/10 mb-6">
            <button className="flex-1 pb-3 font-bold border-b-2 border-primary text-primary">Giriş Yap</button>
            <button className="flex-1 pb-3 font-medium text-muted-foreground hover:text-foreground transition-colors">Hesap Oluştur</button>
          </div>

          <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
            <div className="space-y-1">
              <input type="email" placeholder="E-posta adresiniz" className="w-full bg-secondary/50 border border-white/10 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-1 focus:ring-primary transition-all" />
            </div>
            <div className="space-y-1">
              <input type="password" placeholder="Şifreniz" className="w-full bg-secondary/50 border border-white/10 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-1 focus:ring-primary transition-all" />
            </div>
            
            <div className="flex items-center justify-between py-2">
              <label className="flex items-center text-sm text-muted-foreground cursor-pointer">
                <input type="checkbox" className="mr-2 accent-primary" /> Beni hatırla
              </label>
              <a href="#" className="text-sm text-primary hover:underline">Şifremi unuttum</a>
            </div>

            <button className="w-full bg-primary text-primary-foreground font-bold py-3 rounded-lg hover:bg-primary/90 transition-all shadow-[0_0_15px_rgba(204,255,0,0.2)] hover:shadow-[0_0_25px_rgba(204,255,0,0.4)]">
              Giriş Yap
            </button>
          </form>

          <div className="mt-8 text-center text-xs text-muted-foreground">
            Giriş yaparak <a href="#" className="text-primary hover:underline">Kullanım Koşulları</a> ve <a href="#" className="text-primary hover:underline">Gizlilik Politikasını</a> kabul etmiş olursunuz.
          </div>
        </motion.div>
      </div>

    </div>
  );
}
