import { useState, useEffect, useRef, useCallback } from 'react'

/* ═══════════════════════════════════════════════════════════════
   PARTICLES CANVAS
═══════════════════════════════════════════════════════════════ */
function ParticlesCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animId: number
    const particles: { x: number; y: number; vx: number; vy: number; r: number; alpha: number; color: string }[] = []
    const colors = ['rgba(59,130,246,', 'rgba(34,211,238,', 'rgba(139,92,246,']

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }
    resize()
    window.addEventListener('resize', resize)

    for (let i = 0; i < 80; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        r: Math.random() * 1.5 + 0.5,
        alpha: Math.random() * 0.5 + 0.1,
        color: colors[Math.floor(Math.random() * colors.length)],
      })
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      particles.forEach(p => {
        p.x += p.vx
        p.y += p.vy
        if (p.x < 0) p.x = canvas.width
        if (p.x > canvas.width) p.x = 0
        if (p.y < 0) p.y = canvas.height
        if (p.y > canvas.height) p.y = 0

        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = `${p.color}${p.alpha})`
        ctx.fill()
      })

      // Draw connections
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x
          const dy = particles[i].y - particles[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < 120) {
            ctx.beginPath()
            ctx.moveTo(particles[i].x, particles[i].y)
            ctx.lineTo(particles[j].x, particles[j].y)
            ctx.strokeStyle = `rgba(59,130,246,${0.08 * (1 - dist / 120)})`
            ctx.lineWidth = 0.5
            ctx.stroke()
          }
        }
      }

      animId = requestAnimationFrame(draw)
    }
    draw()

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 pointer-events-none"
      style={{ zIndex: 0 }}
    />
  )
}

/* ═══════════════════════════════════════════════════════════════
   CLOUD ARCHITECTURE SVG VISUALIZATION
═══════════════════════════════════════════════════════════════ */
function CloudArchViz() {
  return (
    <div className="relative w-full max-w-xl mx-auto animate-float" style={{ height: 420 }}>
      <svg viewBox="0 0 500 420" className="w-full h-full" fill="none">
        {/* Defs */}
        <defs>
          <radialGradient id="nodeGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#3B82F6" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#3B82F6" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="nodeCyan" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#22D3EE" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#22D3EE" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="nodePurp" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#8B5CF6" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#8B5CF6" stopOpacity="0" />
          </radialGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <filter id="glow-strong">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>

        {/* Outer orbit ring */}
        <circle cx="250" cy="210" r="150" stroke="rgba(59,130,246,0.08)" strokeWidth="1" strokeDasharray="4 8" />
        <circle cx="250" cy="210" r="110" stroke="rgba(139,92,246,0.06)" strokeWidth="1" strokeDasharray="2 6" />

        {/* Connection lines - animated dashes */}
        {/* Central to top */}
        <line x1="250" y1="210" x2="250" y2="80" stroke="url(#lineBlue)" strokeWidth="1.5" strokeDasharray="6 4" className="animate-dash-flow" opacity="0.7" />
        {/* Central to bottom-left */}
        <line x1="250" y1="210" x2="110" y2="320" stroke="rgba(34,211,238,0.5)" strokeWidth="1.5" strokeDasharray="6 4" className="animate-dash-flow" opacity="0.7" style={{ animationDelay: '0.4s' }} />
        {/* Central to bottom-right */}
        <line x1="250" y1="210" x2="390" y2="320" stroke="rgba(139,92,246,0.5)" strokeWidth="1.5" strokeDasharray="6 4" className="animate-dash-flow" opacity="0.7" style={{ animationDelay: '0.8s' }} />
        {/* Central to left */}
        <line x1="250" y1="210" x2="100" y2="190" stroke="rgba(59,130,246,0.4)" strokeWidth="1" strokeDasharray="4 6" className="animate-dash-flow" opacity="0.5" style={{ animationDelay: '0.2s' }} />
        {/* Central to right */}
        <line x1="250" y1="210" x2="400" y2="190" stroke="rgba(34,211,238,0.4)" strokeWidth="1" strokeDasharray="4 6" className="animate-dash-flow" opacity="0.5" style={{ animationDelay: '0.6s' }} />
        {/* Cross connections */}
        <line x1="250" y1="80" x2="390" y2="320" stroke="rgba(59,130,246,0.15)" strokeWidth="0.5" strokeDasharray="3 8" />
        <line x1="250" y1="80" x2="110" y2="320" stroke="rgba(139,92,246,0.15)" strokeWidth="0.5" strokeDasharray="3 8" />

        {/* ── Central AI node ── */}
        <circle cx="250" cy="210" r="40" fill="url(#nodeGlow)" />
        <circle cx="250" cy="210" r="28" fill="rgba(5,8,22,0.9)" stroke="rgba(59,130,246,0.7)" strokeWidth="1.5" filter="url(#glow)" />
        <circle cx="250" cy="210" r="22" fill="rgba(59,130,246,0.08)" stroke="rgba(59,130,246,0.3)" strokeWidth="0.5" />
        {/* AI icon in center */}
        <text x="250" y="215" textAnchor="middle" fontSize="14" fill="#3B82F6" fontFamily="Outfit" fontWeight="700">AI</text>
        <circle cx="250" cy="210" r="4" fill="#22D3EE" className="animate-pulse-glow" />

        {/* ── AWS node (top) ── */}
        <circle cx="250" cy="80" r="30" fill="rgba(5,8,22,0.9)" stroke="rgba(255,153,0,0.6)" strokeWidth="1.5" filter="url(#glow)" />
        <circle cx="250" cy="80" r="22" fill="rgba(255,153,0,0.05)" />
        <text x="250" y="75" textAnchor="middle" fontSize="8" fill="#FF9900" fontFamily="Arial" fontWeight="900">AWS</text>
        <text x="250" y="86" textAnchor="middle" fontSize="6" fill="rgba(255,153,0,0.7)" fontFamily="Outfit">EC2 • S3 • RDS</text>
        {/* Pulse ring */}
        <circle cx="250" cy="80" r="34" fill="none" stroke="rgba(255,153,0,0.15)" strokeWidth="1" className="animate-ping-slow" style={{ transformOrigin: '250px 80px' }} />

        {/* ── Azure node (bottom-left) ── */}
        <circle cx="110" cy="320" r="30" fill="rgba(5,8,22,0.9)" stroke="rgba(0,120,212,0.6)" strokeWidth="1.5" filter="url(#glow)" />
        <circle cx="110" cy="320" r="22" fill="rgba(0,120,212,0.05)" />
        <text x="110" y="316" textAnchor="middle" fontSize="7.5" fill="#0078D4" fontFamily="Outfit" fontWeight="700">Azure</text>
        <text x="110" y="327" textAnchor="middle" fontSize="6" fill="rgba(0,120,212,0.7)" fontFamily="Outfit">VMs • Blobs</text>
        <circle cx="110" cy="320" r="34" fill="none" stroke="rgba(0,120,212,0.12)" strokeWidth="1" className="animate-ping-slow" style={{ transformOrigin: '110px 320px', animationDelay: '0.7s' }} />

        {/* ── GCP node (bottom-right) ── */}
        <circle cx="390" cy="320" r="30" fill="rgba(5,8,22,0.9)" stroke="rgba(52,168,83,0.6)" strokeWidth="1.5" filter="url(#glow)" />
        <circle cx="390" cy="320" r="22" fill="rgba(52,168,83,0.05)" />
        <text x="390" y="316" textAnchor="middle" fontSize="7.5" fill="#34A853" fontFamily="Outfit" fontWeight="700">GCP</text>
        <text x="390" y="327" textAnchor="middle" fontSize="6" fill="rgba(52,168,83,0.7)" fontFamily="Outfit">GCE • BigQuery</text>
        <circle cx="390" cy="320" r="34" fill="none" stroke="rgba(52,168,83,0.12)" strokeWidth="1" className="animate-ping-slow" style={{ transformOrigin: '390px 320px', animationDelay: '1.4s' }} />

        {/* ── Left node (Cost) ── */}
        <circle cx="100" cy="190" r="22" fill="rgba(5,8,22,0.9)" stroke="rgba(34,211,238,0.5)" strokeWidth="1" filter="url(#glow)" />
        <text x="100" y="187" textAnchor="middle" fontSize="6.5" fill="#22D3EE" fontFamily="Outfit" fontWeight="600">Cost</text>
        <text x="100" y="196" textAnchor="middle" fontSize="6.5" fill="#22D3EE" fontFamily="Outfit" fontWeight="600">Forecast</text>

        {/* ── Right node (Rec) ── */}
        <circle cx="400" cy="190" r="22" fill="rgba(5,8,22,0.9)" stroke="rgba(139,92,246,0.5)" strokeWidth="1" filter="url(#glow)" />
        <text x="400" y="187" textAnchor="middle" fontSize="6.5" fill="#8B5CF6" fontFamily="Outfit" fontWeight="600">AI Rec</text>
        <text x="400" y="196" textAnchor="middle" fontSize="6.5" fill="#8B5CF6" fontFamily="Outfit" fontWeight="600">Engine</text>

        {/* Neural network dots */}
        {[[180,140],[200,170],[220,130],[280,140],[300,170],[320,130],[250,155]].map(([cx,cy],i) => (
          <circle key={i} cx={cx} cy={cy} r="2" fill="#3B82F6" opacity="0.4" className="animate-pulse-glow" style={{ animationDelay: `${i*0.3}s` }} />
        ))}
        {[[180,140],[200,170],[250,155]].map(([x1,y1],i) => (
          <line key={i} x1={x1} y1={y1} x2="250" y2="155" stroke="rgba(59,130,246,0.2)" strokeWidth="0.5" />
        ))}
        {[[280,140],[300,170],[250,155]].map(([x1,y1],i) => (
          <line key={i} x1={x1} y1={y1} x2="250" y2="155" stroke="rgba(139,92,246,0.2)" strokeWidth="0.5" />
        ))}
      </svg>

      {/* Floating metric badges */}
      <div className="absolute top-0 right-0 glass-blue rounded-xl px-3 py-2 animate-float-delay" style={{ zIndex: 10 }}>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse-glow" />
          <span className="text-xs text-cyan-300 font-mono font-semibold">−38% cost</span>
        </div>
      </div>
      <div className="absolute bottom-8 left-0 glass-purple rounded-xl px-3 py-2 animate-float" style={{ zIndex: 10, animationDelay: '0.8s' }}>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse-glow" />
          <span className="text-xs text-purple-300 font-mono font-semibold">AI Rec: Active</span>
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   SECTION HEADER (reusable)
═══════════════════════════════════════════════════════════════ */
function SectionHeader({
  eyebrow, title, gradTitle, subtitle, align = 'center'
}: {
  eyebrow: string
  title: string
  gradTitle?: string
  subtitle?: string
  align?: 'center' | 'left'
}) {
  return (
    <div className={`mb-16 ${align === 'center' ? 'text-center max-w-3xl mx-auto' : 'max-w-2xl'}`}>
      <div className="inline-flex items-center gap-2 glass-blue rounded-full px-4 py-1.5 mb-5">
        <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse-glow" />
        <span className="text-xs font-semibold text-cyan-300 uppercase tracking-widest">{eyebrow}</span>
      </div>
      <h2 className="text-4xl sm:text-5xl font-bold text-white mb-4" style={{ lineHeight: 1.1 }}>
        {title}{' '}
        {gradTitle && <span className="grad-blue-cyan">{gradTitle}</span>}
      </h2>
      {subtitle && <p className="text-slate-400 text-lg leading-relaxed">{subtitle}</p>}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   NAVBAR
═══════════════════════════════════════════════════════════════ */
function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 30)
    window.addEventListener('scroll', fn)
    return () => window.removeEventListener('scroll', fn)
  }, [])

  const links = ['Features', 'How It Works', 'Pricing', 'FAQ']

  return (
    <header className={`fixed top-0 inset-x-0 z-50 transition-all duration-500 ${scrolled ? 'py-3' : 'py-5'}`}>
      <div className={`mx-4 sm:mx-auto sm:max-w-6xl transition-all duration-500 ${scrolled ? 'glass rounded-2xl px-5 py-3' : 'px-6'}`}
        style={scrolled ? { border: '1px solid rgba(59,130,246,0.2)', boxShadow: '0 4px 40px rgba(0,0,0,0.5)' } : {}}>
        <nav className="flex items-center justify-between">
          {/* Logo */}
          <a href="#" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'linear-gradient(135deg,#3B82F6,#22D3EE)', boxShadow: '0 0 20px rgba(59,130,246,0.5)' }}>
              <svg viewBox="0 0 20 20" className="w-4 h-4" fill="none">
                <path d="M17 10a5 5 0 0 0-4.9-5A4.5 4.5 0 0 0 3.5 8.5 3.5 3.5 0 0 0 5 15h12a3 3 0 0 0 0-6z" stroke="white" strokeWidth="1.5" strokeLinejoin="round" />
              </svg>
            </div>
            <span className="text-lg font-bold font-display text-white tracking-tight">
              Cloud<span className="grad-blue-cyan">Wise</span>
            </span>
          </a>

          {/* Desktop links */}
          <div className="hidden md:flex items-center gap-8">
            {links.map(l => (
              <a key={l} href={`#${l.toLowerCase().replace(/\s+/g,'-')}`}
                className="nav-link text-sm text-slate-400 hover:text-white transition-colors font-medium">
                {l}
              </a>
            ))}
          </div>

          {/* CTA */}
          <div className="hidden md:flex items-center gap-3">
            <a href="#" className="text-sm font-medium text-slate-400 hover:text-white transition-colors px-3 py-2">
              Sign in
            </a>
            <a href="#" className="btn-primary text-sm font-semibold text-white px-5 py-2.5 rounded-xl">
              Get Started Free
            </a>
          </div>

          {/* Mobile burger */}
          <button onClick={() => setMenuOpen(!menuOpen)} className="md:hidden text-slate-400 hover:text-white p-2">
            <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2">
              {menuOpen
                ? <><line x1="18" y1="6" x2="6" y2="18" strokeLinecap="round"/><line x1="6" y1="6" x2="18" y2="18" strokeLinecap="round"/></>
                : <><line x1="3" y1="6" x2="21" y2="6" strokeLinecap="round"/><line x1="3" y1="12" x2="21" y2="12" strokeLinecap="round"/><line x1="3" y1="18" x2="21" y2="18" strokeLinecap="round"/></>
              }
            </svg>
          </button>
        </nav>

        {menuOpen && (
          <div className="md:hidden mt-4 pb-4 border-t border-white/5 pt-4 space-y-2">
            {links.map(l => (
              <a key={l} href={`#${l.toLowerCase().replace(/\s+/g,'-')}`}
                onClick={() => setMenuOpen(false)}
                className="block text-sm text-slate-400 hover:text-white py-2 px-3 rounded-lg hover:bg-white/5 transition-colors">
                {l}
              </a>
            ))}
            <div className="flex flex-col gap-2 pt-2">
              <a href="#" className="btn-outline text-sm text-center font-medium text-white py-2.5 px-4 rounded-xl">Sign in</a>
              <a href="#" className="btn-primary text-sm text-center font-semibold text-white py-2.5 px-4 rounded-xl">Get Started</a>
            </div>
          </div>
        )}
      </div>
    </header>
  )
}

/* ═══════════════════════════════════════════════════════════════
   HERO
═══════════════════════════════════════════════════════════════ */
function Hero() {
  return (
    <section className="relative min-h-screen flex flex-col justify-center overflow-hidden pt-20">
      {/* Layers */}
      <div className="absolute inset-0 grid-bg opacity-100" />
      <ParticlesCanvas />
      <div className="absolute inset-0 aurora-hero" />

      {/* Glow orbs */}
      <div className="glow-orb absolute w-[600px] h-[600px] opacity-20 animate-pulse-glow" style={{ background: '#3B82F6', top: '-200px', left: '-200px' }} />
      <div className="glow-orb absolute w-[400px] h-[400px] opacity-15" style={{ background: '#8B5CF6', bottom: '-100px', right: '-100px', animation: 'aurora-shift 8s ease-in-out infinite' }} />
      <div className="glow-orb absolute w-[300px] h-[300px] opacity-10" style={{ background: '#22D3EE', top: '30%', right: '10%', animation: 'aurora-shift 12s ease-in-out infinite reverse' }} />

      {/* Top glow line */}
      <div className="absolute top-0 inset-x-0 h-px" style={{ background: 'linear-gradient(90deg, transparent, rgba(59,130,246,0.6), rgba(34,211,238,0.4), transparent)' }} />

      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 w-full">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-8 items-center">
          {/* Left — copy */}
          <div>
            {/* Eyebrow badge */}
            <div className="inline-flex items-center gap-2.5 glass-cyan rounded-full px-4 py-2 mb-7 badge-glow">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse-glow" />
              <span className="text-xs font-semibold text-cyan-300 uppercase tracking-widest font-mono">AI-Powered Cloud Intelligence</span>
              <span className="text-xs text-cyan-400/60">v2.0</span>
            </div>

            {/* Headline */}
            <h1 className="text-5xl sm:text-6xl xl:text-7xl font-black text-white mb-6 leading-[1.02] tracking-tight">
              Build Smarter
              <br />
              <span className="grad-blue-cyan text-glow-blue">Cloud</span>
              <br />
              <span className="grad-cyan-purple">Infrastructure</span>
              <br />
              <span className="text-white">with AI</span>
            </h1>

            {/* Sub */}
            <p className="text-slate-400 text-lg leading-relaxed mb-9 max-w-xl">
              Estimate resources, compare AWS, Azure & Google Cloud, forecast costs, and receive
              AI-powered deployment recommendations — all in one intelligent platform.
            </p>

            {/* CTAs */}
            <div className="flex flex-col sm:flex-row gap-4 mb-10">
              <a href="#" className="btn-primary group inline-flex items-center justify-center gap-2 text-base font-bold text-white px-7 py-4 rounded-2xl">
                Get Started Free
                <svg viewBox="0 0 20 20" className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="4" y1="10" x2="16" y2="10" strokeLinecap="round"/>
                  <polyline points="10 4 16 10 10 16" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </a>
              <a href="#" className="btn-outline group inline-flex items-center justify-center gap-3 text-base font-semibold text-white px-7 py-4 rounded-2xl">
                <span className="w-8 h-8 flex items-center justify-center rounded-full" style={{ background: 'rgba(255,255,255,0.1)' }}>
                  <svg viewBox="0 0 20 20" className="w-4 h-4" fill="white"><polygon points="7,4 17,10 7,16"/></svg>
                </span>
                Watch Demo
              </a>
            </div>

            {/* Stats row */}
            <div className="flex items-center gap-6 flex-wrap">
              {[
                { value: '40%', label: 'Cost Savings' },
                { value: '2.4k+', label: 'Companies' },
                { value: '3', label: 'Cloud Providers' },
              ].map((s, i) => (
                <div key={i} className="flex items-center gap-3">
                  {i > 0 && <div className="w-px h-8 bg-white/10" />}
                  <div>
                    <p className="text-xl font-black text-white font-display grad-blue-cyan">{s.value}</p>
                    <p className="text-xs text-slate-500">{s.label}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right — visualization */}
          <div className="relative">
            <CloudArchViz />
          </div>
        </div>

        {/* Bottom floating cards row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-16">
          {[
            { icon: '⚡', label: 'Instant Analysis', value: '<30 min to first rec', color: 'border-blue-500/20', glow: 'blue' },
            { icon: '🎯', label: 'Precision Forecast', value: '94.2% accuracy rate', color: 'border-cyan-500/20', glow: 'cyan' },
            { icon: '🛡️', label: 'Enterprise Secure', value: 'SOC 2 Type II certified', color: 'border-purple-500/20', glow: 'purple' },
          ].map((c) => (
            <div key={c.label} className={`glass rounded-2xl px-5 py-4 flex items-center gap-4 card-hover card-hover-${c.glow}`} style={{ border: `1px solid`, borderColor: c.color.replace('border-','').replace('/20','') }}>
              <span className="text-2xl">{c.icon}</span>
              <div>
                <p className="text-sm font-semibold text-white">{c.label}</p>
                <p className="text-xs text-slate-500 font-mono">{c.value}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════
   TRUSTED BY
═══════════════════════════════════════════════════════════════ */
function TrustedBy() {
  const companies = ['Stripe','Notion','Vercel','Linear','Figma','Loom','Retool','Deno','Supabase','Railway']

  return (
    <section className="relative py-16 overflow-hidden">
      <div className="section-divider mb-0" />
      <div className="py-14" style={{ background: 'linear-gradient(180deg, rgba(5,8,22,0) 0%, rgba(10,15,46,0.5) 50%, rgba(5,8,22,0) 100%)' }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-center text-xs font-semibold text-slate-600 uppercase tracking-widest mb-8 font-mono">
            Trusted by engineering teams at
          </p>
          <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-4">
            {companies.map(name => (
              <span key={name} className="text-lg font-bold text-slate-700 hover:text-slate-500 transition-colors tracking-tight font-display cursor-default select-none">
                {name}
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="section-divider" />
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════
   CLOUD PROVIDERS
═══════════════════════════════════════════════════════════════ */
function CloudProviders() {
  const providers = [
    {
      name: 'Amazon Web Services',
      abbr: 'AWS',
      color: '#FF9900',
      glow: 'rgba(255,153,0,0.2)',
      border: 'rgba(255,153,0,0.2)',
      hoverClass: '',
      services: ['EC2 Compute', 'S3 Storage', 'RDS Database', 'Lambda Serverless', 'CloudFront CDN'],
      metric: '200+ services analyzed',
      savings: 'Avg. 34% savings',
      icon: (
        <text x="50%" y="55%" dominantBaseline="middle" textAnchor="middle" fontSize="22" fontWeight="900" fontFamily="Arial" fill="#FF9900">AWS</text>
      ),
    },
    {
      name: 'Microsoft Azure',
      abbr: 'Azure',
      color: '#0078D4',
      glow: 'rgba(0,120,212,0.2)',
      border: 'rgba(0,120,212,0.2)',
      services: ['Virtual Machines', 'Blob Storage', 'Azure SQL', 'App Service', 'Azure CDN'],
      metric: '180+ services analyzed',
      savings: 'Avg. 38% savings',
      icon: (
        <path d="M22 36L34 12l12 24H22z" fill="#0078D4" />
      ),
    },
    {
      name: 'Google Cloud Platform',
      abbr: 'GCP',
      color: '#34A853',
      glow: 'rgba(52,168,83,0.2)',
      border: 'rgba(52,168,83,0.2)',
      services: ['Compute Engine', 'Cloud Storage', 'BigQuery', 'Cloud Run', 'Firebase'],
      metric: '150+ services analyzed',
      savings: 'Avg. 41% savings',
      icon: (
        <>
          <circle cx="50%" cy="50%" r="18" fill="none" stroke="#4285F4" strokeWidth="4"/>
          <path d="M34 24 A18 18 0 0 1 52 24" stroke="#EA4335" strokeWidth="4" strokeLinecap="round" fill="none"/>
          <path d="M52 24 A18 18 0 0 1 66 38" stroke="#FBBC04" strokeWidth="4" strokeLinecap="round" fill="none"/>
          <path d="M66 38 A18 18 0 0 1 34 38" stroke="#34A853" strokeWidth="4" strokeLinecap="round" fill="none"/>
        </>
      ),
    },
  ]

  return (
    <section className="relative py-24 overflow-hidden">
      <div className="absolute inset-0 aurora-section" />
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="Cloud Providers"
          title="Unified intelligence across"
          gradTitle="every major cloud"
          subtitle="CloudWise speaks the language of AWS, Azure, and GCP natively — comparing, estimating, and optimizing across all three simultaneously."
        />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {providers.map((p) => (
            <div
              key={p.name}
              className="glass card-hover rounded-3xl p-7 flex flex-col group cursor-default"
              style={{ border: `1px solid ${p.border}`, transition: 'all 0.3s ease' }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.boxShadow = `0 8px 60px ${p.glow}, 0 0 100px ${p.glow.replace('0.2','0.05')}`; (e.currentTarget as HTMLElement).style.borderColor = p.color + '55' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.boxShadow = ''; (e.currentTarget as HTMLElement).style.borderColor = p.border }}
            >
              {/* Logo */}
              <div className="w-16 h-16 rounded-2xl mb-5 flex items-center justify-center" style={{ background: `${p.glow}`, border: `1px solid ${p.border}` }}>
                <svg viewBox="0 0 80 60" className="w-14 h-10">{p.icon}</svg>
              </div>
              <h3 className="text-xl font-bold text-white mb-1">{p.name}</h3>
              <p className="text-xs font-mono mb-5" style={{ color: p.color }}>{p.metric}</p>

              {/* Services */}
              <div className="flex-1 space-y-2 mb-5">
                {p.services.map(s => (
                  <div key={s} className="flex items-center gap-2.5">
                    <svg viewBox="0 0 12 12" className="w-3 h-3 shrink-0"><circle cx="6" cy="6" r="2" fill={p.color} /></svg>
                    <span className="text-sm text-slate-400">{s}</span>
                  </div>
                ))}
              </div>

              {/* Badge */}
              <div className="flex items-center justify-between pt-4 border-t" style={{ borderColor: `${p.border}` }}>
                <span className="text-sm font-bold" style={{ color: p.color }}>{p.savings}</span>
                <span className="text-xs font-mono text-slate-600">per analyzed workload</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════
   FEATURES
═══════════════════════════════════════════════════════════════ */
function Features() {
  const features = [
    {
      icon: '🧠',
      title: 'AI Resource Estimation',
      desc: 'Describe your workload in plain English. CloudWise\'s AI models translate your requirements into precise instance types, storage, and network configurations.',
      tag: 'GPT-4o Powered',
      color: 'blue',
    },
    {
      icon: '⚖️',
      title: 'Multi-Cloud Comparison',
      desc: 'Side-by-side cost and performance analysis across AWS, Azure, and GCP. Know exactly which provider wins for each specific workload.',
      tag: '3 Providers',
      color: 'cyan',
    },
    {
      icon: '📈',
      title: 'Cost Forecasting',
      desc: '12-month spend projections using ML models trained on $4B+ of cloud billing data. Accurate to within 3% for stable workloads.',
      tag: '94% Accuracy',
      color: 'purple',
    },
    {
      icon: '🎯',
      title: 'Smart Recommendations',
      desc: 'Receive a prioritized action queue with projected ROI for every optimization — from right-sizing to Reserved Instance purchases.',
      tag: 'Prioritized Queue',
      color: 'blue',
    },
    {
      icon: '🔍',
      title: 'Anomaly Detection',
      desc: 'Real-time alerts when spend deviates from projected patterns. Catch runaway costs before they hit your bill.',
      tag: 'Real-Time',
      color: 'cyan',
    },
    {
      icon: '🔐',
      title: 'Enterprise Security',
      desc: 'Read-only IAM access. SOC 2 Type II certified. Zero data exfiltration. Every action is audited and reversible.',
      tag: 'SOC 2 Type II',
      color: 'purple',
    },
  ]

  const colorMap: Record<string, { bg: string; border: string; tag: string }> = {
    blue:   { bg: 'rgba(59,130,246,0.08)',  border: 'rgba(59,130,246,0.2)',  tag: 'text-blue-400 bg-blue-500/10 border-blue-500/20' },
    cyan:   { bg: 'rgba(34,211,238,0.07)',  border: 'rgba(34,211,238,0.18)', tag: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20' },
    purple: { bg: 'rgba(139,92,246,0.07)', border: 'rgba(139,92,246,0.18)', tag: 'text-purple-400 bg-purple-500/10 border-purple-500/20' },
  }

  return (
    <section id="features" className="relative py-24 overflow-hidden">
      <div className="absolute inset-0 grid-bg opacity-40" />
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="Platform Capabilities"
          title="Six AI pillars that"
          gradTitle="transform your cloud"
          subtitle="From estimation to optimization, CloudWise covers the complete cloud intelligence lifecycle in one unified platform."
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {features.map((f) => {
            const c = colorMap[f.color]
            return (
              <div
                key={f.title}
                className="card-hover rounded-2xl p-6 flex flex-col cursor-default group"
                style={{ background: 'rgba(255,255,255,0.02)', border: `1px solid ${c.border}`, backdropFilter: 'blur(10px)', transition: 'all 0.3s ease' }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = c.bg }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.02)' }}
              >
                <div className="text-3xl mb-4">{f.icon}</div>
                <div className="flex items-start justify-between gap-2 mb-3">
                  <h3 className="text-base font-bold text-white">{f.title}</h3>
                  <span className={`shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full border font-mono ${c.tag}`}>{f.tag}</span>
                </div>
                <p className="text-sm text-slate-500 leading-relaxed flex-1">{f.desc}</p>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════
   HOW IT WORKS
═══════════════════════════════════════════════════════════════ */
function HowItWorks() {
  const steps = [
    {
      num: '01',
      icon: '🔌',
      title: 'Connect Your Clouds',
      desc: 'Link AWS, Azure, or GCP in under 3 minutes using our secure read-only IAM integration. No agents, no code changes, no interruptions.',
      detail: 'Supports AWS Organizations, Azure Tenants, GCP Folders. Multi-account out of the box.',
      color: '#3B82F6',
    },
    {
      num: '02',
      icon: '🤖',
      title: 'AI Scans & Learns',
      desc: 'Our AI ingests billing data, usage metrics, and workload patterns — benchmarking against $4B+ of cloud spend data from 2,400+ companies.',
      detail: 'Full analysis delivered in under 30 minutes for most accounts.',
      color: '#8B5CF6',
    },
    {
      num: '03',
      icon: '💡',
      title: 'Act on Intelligence',
      desc: 'Receive a prioritized recommendation queue with projected savings for each item. One-click apply or export to Terraform — fully audited.',
      detail: 'Average team applies first optimization within 45 minutes of onboarding.',
      color: '#22D3EE',
    },
  ]

  return (
    <section id="how-it-works" className="relative py-24 overflow-hidden">
      <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, #050816 0%, #0a0f2e 50%, #050816 100%)' }} />
      <div className="absolute inset-0 aurora-section opacity-60" />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="How It Works"
          title="From connection to"
          gradTitle="savings in 30 minutes"
          subtitle="The fastest path from cloud confusion to cloud confidence. Three steps, zero infrastructure changes."
        />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 relative">
          {/* Connector line */}
          <div className="hidden lg:block absolute top-16 left-[17%] right-[17%] h-px" style={{ background: 'linear-gradient(90deg, #3B82F6, #8B5CF6, #22D3EE)', opacity: 0.3 }} />

          {steps.map((step, i) => (
            <div key={step.num} className="relative">
              {/* Number badge */}
              <div className="relative z-10 w-14 h-14 rounded-2xl flex items-center justify-center mb-6 mx-auto lg:mx-0 font-black text-white font-display text-lg"
                style={{ background: `linear-gradient(135deg, ${step.color}30, ${step.color}10)`, border: `1px solid ${step.color}40`, boxShadow: `0 0 30px ${step.color}25` }}>
                <span style={{ color: step.color }}>{step.num}</span>
              </div>

              <div className="glass rounded-3xl p-7 h-full"
                style={{ border: `1px solid ${step.color}20`, transition: 'all 0.3s ease' }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = step.color + '50'; (e.currentTarget as HTMLElement).style.boxShadow = `0 0 40px ${step.color}15` }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = step.color + '20'; (e.currentTarget as HTMLElement).style.boxShadow = '' }}>
                <div className="text-3xl mb-4">{step.icon}</div>
                <h3 className="text-xl font-bold text-white mb-3">{step.title}</h3>
                <p className="text-sm text-slate-400 leading-relaxed mb-5">{step.desc}</p>
                <div className="flex items-start gap-2 rounded-xl p-3" style={{ background: `${step.color}0a`, border: `1px solid ${step.color}15` }}>
                  <span className="font-mono text-xs mt-0.5" style={{ color: step.color }}>→</span>
                  <p className="text-xs font-mono" style={{ color: step.color + 'cc' }}>{step.detail}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════
   AI RECOMMENDATION PREVIEW
═══════════════════════════════════════════════════════════════ */
function AIRecommendationPreview() {
  const [activeRec, setActiveRec] = useState(0)

  const recommendations = [
    {
      id: 'REC-0041',
      type: 'Right-Size',
      provider: 'AWS',
      resource: 'EC2 t3.xlarge → t3.medium',
      reason: 'CPU utilization averaged 12% over 30 days. Workload profile indicates t3.medium is sufficient with 2× headroom.',
      saving: '$340/mo',
      confidence: 97,
      effort: 'Low',
      priority: 'Critical',
      impact: 'High',
    },
    {
      id: 'REC-0042',
      type: 'Reserved Instance',
      provider: 'GCP',
      resource: 'BigQuery → Reserved Slots',
      reason: 'Query patterns show consistent 80% slot utilization. 1-year reservation reduces per-query cost by 59%.',
      saving: '$820/mo',
      confidence: 94,
      effort: 'Low',
      priority: 'High',
      impact: 'Critical',
    },
    {
      id: 'REC-0043',
      type: 'Auto-Scale',
      provider: 'Azure',
      resource: 'App Service Plan B2 → Auto-Scale',
      reason: 'Traffic analysis shows 6-hour peak windows daily. Dynamic scaling would eliminate over-provisioned idle capacity.',
      saving: '$190/mo',
      confidence: 91,
      effort: 'Medium',
      priority: 'Medium',
      impact: 'Medium',
    },
  ]

  const rec = recommendations[activeRec]

  const priorityColors: Record<string, string> = { Critical: '#EF4444', High: '#F59E0B', Medium: '#3B82F6' }

  return (
    <section className="relative py-24 overflow-hidden">
      <div className="absolute inset-0 grid-bg opacity-30" />
      <div className="glow-orb absolute w-[500px] h-[500px] opacity-10 -right-40 top-1/2 -translate-y-1/2" style={{ background: '#8B5CF6' }} />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="AI Intelligence"
          title="Recommendations that"
          gradTitle="actually ship savings"
          subtitle="Real AI-generated optimization cards — each with confidence scores, projected savings, and one-click apply."
        />

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Left — list */}
          <div className="lg:col-span-2 space-y-3">
            {recommendations.map((r, i) => (
              <button
                key={r.id}
                onClick={() => setActiveRec(i)}
                className="w-full text-left rounded-2xl p-4 transition-all duration-200"
                style={{
                  background: activeRec === i ? 'rgba(59,130,246,0.1)' : 'rgba(255,255,255,0.02)',
                  border: `1px solid ${activeRec === i ? 'rgba(59,130,246,0.4)' : 'rgba(255,255,255,0.06)'}`,
                  boxShadow: activeRec === i ? '0 0 30px rgba(59,130,246,0.1)' : '',
                }}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-mono text-slate-600">{r.id}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-500 bg-white/5 px-2 py-0.5 rounded font-mono">{r.provider}</span>
                    <span className="text-xs font-bold rounded-full px-2 py-0.5" style={{ color: priorityColors[r.priority], background: `${priorityColors[r.priority]}15` }}>{r.priority}</span>
                  </div>
                </div>
                <p className="text-sm font-semibold text-white mb-1">{r.resource}</p>
                <p className="text-xs text-slate-500">{r.type} · <span className="text-emerald-400 font-bold">{r.saving}</span></p>
              </button>
            ))}
          </div>

          {/* Right — detail */}
          <div className="lg:col-span-3">
            <div className="glass-blue rounded-3xl p-7 h-full relative overflow-hidden scan-overlay" style={{ border: '1px solid rgba(59,130,246,0.2)', minHeight: 360 }}>
              {/* Header */}
              <div className="flex items-start justify-between mb-5">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs font-mono text-blue-400">{rec.id}</span>
                    <span className="text-xs font-bold bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded-full border border-blue-500/20">{rec.type}</span>
                    <span className="text-xs font-bold bg-white/5 text-slate-400 px-2 py-0.5 rounded-full">{rec.provider}</span>
                  </div>
                  <h3 className="text-xl font-bold text-white">{rec.resource}</h3>
                </div>
                <div className="text-right">
                  <p className="text-2xl font-black text-emerald-400 font-display">{rec.saving}</p>
                  <p className="text-xs text-slate-500">projected savings</p>
                </div>
              </div>

              {/* AI reasoning */}
              <div className="rounded-xl p-4 mb-5" style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)' }}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse-glow" />
                  <span className="text-xs font-mono text-cyan-400 font-semibold">AI REASONING</span>
                </div>
                <p className="text-sm text-slate-300 leading-relaxed font-mono">{rec.reason}</p>
              </div>

              {/* Metrics row */}
              <div className="grid grid-cols-3 gap-3 mb-5">
                {[
                  { label: 'Confidence', value: `${rec.confidence}%`, color: '#22D3EE' },
                  { label: 'Effort', value: rec.effort, color: '#8B5CF6' },
                  { label: 'Impact', value: rec.impact, color: '#3B82F6' },
                ].map(m => (
                  <div key={m.label} className="rounded-xl p-3 text-center" style={{ background: `${m.color}10`, border: `1px solid ${m.color}20` }}>
                    <p className="text-xs text-slate-500 mb-1">{m.label}</p>
                    <p className="text-base font-bold font-display" style={{ color: m.color }}>{m.value}</p>
                  </div>
                ))}
              </div>

              {/* Confidence bar */}
              <div className="mb-5">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs text-slate-500">AI Confidence Score</span>
                  <span className="text-xs font-mono text-cyan-400">{rec.confidence}%</span>
                </div>
                <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                  <div className="h-full rounded-full metric-bar transition-all duration-500" style={{ width: `${rec.confidence}%` }} />
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <button className="btn-primary flex-1 text-sm font-bold text-white py-3 rounded-xl">
                  Apply Recommendation
                </button>
                <button className="btn-outline text-sm font-medium text-slate-300 py-3 px-4 rounded-xl">
                  Export →
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════
   DASHBOARD PREVIEW
═══════════════════════════════════════════════════════════════ */
function DashboardPreview() {
  return (
    <section className="relative py-24 overflow-hidden">
      <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, #050816 0%, #070c24 100%)' }} />
      <div className="glow-orb absolute w-[700px] h-[400px] opacity-10 -left-40 top-1/2 -translate-y-1/2" style={{ background: '#3B82F6' }} />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="Live Dashboard"
          title="Your cloud at a"
          gradTitle="glance — always"
          subtitle="A unified control center for all three clouds. Real-time metrics, spend trends, and AI insights in one view."
        />

        {/* Browser mockup */}
        <div className="rounded-3xl overflow-hidden" style={{ border: '1px solid rgba(59,130,246,0.2)', boxShadow: '0 0 80px rgba(59,130,246,0.1), 0 40px 120px rgba(0,0,0,0.6)' }}>
          {/* Browser bar */}
          <div className="flex items-center gap-2 px-4 py-3" style={{ background: 'rgba(10,15,46,0.9)', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <div className="flex gap-1.5">
              <div className="w-3 h-3 rounded-full bg-red-500/70" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/70" />
              <div className="w-3 h-3 rounded-full bg-green-500/70" />
            </div>
            <div className="flex-1 mx-4 rounded-lg px-3 py-1.5 text-xs text-slate-500 font-mono" style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)' }}>
              https://app.cloudwise.ai/dashboard
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-glow" />
              <span className="text-xs text-emerald-400 font-mono">Live</span>
            </div>
          </div>

          {/* Dashboard content */}
          <div className="p-6" style={{ background: 'rgba(5,8,22,0.95)' }}>
            {/* Top stats */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
              {[
                { label: 'Monthly Spend', value: '$84,320', change: '−12%', delta: 'down', color: '#22D3EE' },
                { label: 'Projected Savings', value: '$28,400', change: '+34%', delta: 'up', color: '#3B82F6' },
                { label: 'Resources Monitored', value: '4,821', change: '+142', delta: 'up', color: '#8B5CF6' },
                { label: 'Active Alerts', value: '3', change: '−7', delta: 'down', color: '#EF4444' },
              ].map(s => (
                <div key={s.label} className="rounded-2xl p-4" style={{ background: `${s.color}08`, border: `1px solid ${s.color}18` }}>
                  <p className="text-xs text-slate-500 mb-1 uppercase tracking-wider font-mono">{s.label}</p>
                  <p className="text-2xl font-black font-display text-white mb-1">{s.value}</p>
                  <p className="text-xs font-mono font-semibold" style={{ color: s.delta === 'up' ? '#22D3EE' : s.color === '#EF4444' ? '#22D3EE' : '#EF4444' }}>{s.change} vs last month</p>
                </div>
              ))}
            </div>

            {/* Middle: chart + recs list */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
              {/* Spend trend chart */}
              <div className="lg:col-span-2 rounded-2xl p-4" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
                <div className="flex items-center justify-between mb-4">
                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Cloud Spend Trend</p>
                  <div className="flex gap-1.5">
                    {['1M','3M','6M','1Y'].map((t, i) => (
                      <button key={t} className="text-[10px] px-2 py-0.5 rounded font-mono" style={{ background: i === 2 ? 'rgba(59,130,246,0.2)' : 'rgba(255,255,255,0.03)', color: i === 2 ? '#3B82F6' : '#64748b', border: `1px solid ${i === 2 ? 'rgba(59,130,246,0.3)' : 'rgba(255,255,255,0.05)'}` }}>{t}</button>
                    ))}
                  </div>
                </div>
                {/* Bar chart */}
                <div className="flex items-end gap-1.5 h-28">
                  {[42,58,51,67,72,60,78,84,70,88,82,94].map((h, i) => (
                    <div key={i} className="flex-1 rounded-sm transition-all group/bar relative" style={{ height: `${h}%` }}>
                      <div className="absolute inset-0 rounded-sm" style={{ background: i === 11 ? 'linear-gradient(to top, #3B82F6, #22D3EE)' : i > 8 ? 'rgba(59,130,246,0.4)' : 'rgba(59,130,246,0.15)' }} />
                    </div>
                  ))}
                </div>
                <div className="flex items-center justify-between mt-2">
                  {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].map(m => (
                    <span key={m} className="text-[9px] text-slate-700 flex-1 text-center font-mono">{m}</span>
                  ))}
                </div>
              </div>

              {/* Provider breakdown */}
              <div className="rounded-2xl p-4" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">Provider Split</p>
                <div className="space-y-3">
                  {[
                    { name: 'AWS', pct: 58, color: '#FF9900', spend: '$48,906' },
                    { name: 'Azure', pct: 24, color: '#0078D4', spend: '$20,237' },
                    { name: 'GCP', pct: 18, color: '#34A853', spend: '$15,177' },
                  ].map(p => (
                    <div key={p.name}>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-bold" style={{ color: p.color }}>{p.name}</span>
                        <span className="text-xs font-mono text-slate-400">{p.spend}</span>
                      </div>
                      <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                        <div className="h-full rounded-full transition-all" style={{ width: `${p.pct}%`, background: p.color, opacity: 0.7 }} />
                      </div>
                      <p className="text-[10px] text-slate-600 mt-1 font-mono">{p.pct}% of total</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Recommendation rows */}
            <div className="rounded-2xl p-4" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Top AI Recommendations</p>
              <div className="space-y-2">
                {[
                  { provider: 'AWS', action: 'Downsize EC2 t3.xlarge fleet (12 instances)', saving: '$4,080/mo', priority: 'Critical', pct: 97 },
                  { provider: 'GCP', action: 'Reserve BigQuery slots for consistent workloads', saving: '$9,840/mo', priority: 'High', pct: 94 },
                  { provider: 'Azure', action: 'Enable auto-scaling on App Service Plan B3', saving: '$2,280/mo', priority: 'High', pct: 91 },
                ].map(r => (
                  <div key={r.action} className="flex items-center justify-between rounded-xl px-3 py-2.5 hover:bg-white/3 transition-colors" style={{ border: '1px solid rgba(255,255,255,0.04)' }}>
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-[10px] font-bold text-slate-500 bg-white/5 rounded px-1.5 py-0.5 font-mono shrink-0">{r.provider}</span>
                      <p className="text-xs text-slate-300 truncate">{r.action}</p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0 ml-3">
                      <div className="w-16 h-1 bg-white/5 rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${r.pct}%`, background: 'linear-gradient(90deg,#3B82F6,#22D3EE)' }} />
                      </div>
                      <span className="text-xs font-bold text-emerald-400 font-mono w-20 text-right">{r.saving}</span>
                      <span className="text-[10px] font-bold rounded-full px-2 py-0.5" style={{ background: r.priority === 'Critical' ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)', color: r.priority === 'Critical' ? '#EF4444' : '#F59E0B' }}>{r.priority}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════
   TESTIMONIALS
═══════════════════════════════════════════════════════════════ */
function Testimonials() {
  const items = [
    {
      quote: "CloudWise found $38,000/month in wasted AWS spend within 48 hours of integration. The AI reasoning engine is genuinely impressive — every recommendation came with a clear, defensible explanation.",
      name: 'Priya Sharma',
      role: 'VP of Engineering',
      company: 'Meridian Analytics',
      avatar: 'PS',
      color: '#8B5CF6',
      metric: '$38k/mo saved',
    },
    {
      quote: "We evaluated 5 cloud cost tools. CloudWise was the only platform that didn't just show dashboards but actually helped us ship changes. The Commitment Manager alone paid for 3 years of subscription in one quarter.",
      name: 'Marcus Chen',
      role: 'Head of Infrastructure',
      company: 'Vanta Labs',
      avatar: 'MC',
      color: '#3B82F6',
      metric: '12× ROI Q1',
    },
    {
      quote: "Our FinOps team moved from weekly manual reviews to daily automated optimizations. CloudWise is the single source of truth for our entire $2M/month cloud budget across AWS, Azure, and GCP.",
      name: 'Sofia Reyes',
      role: 'Director of FinOps',
      company: 'Luminary Health',
      avatar: 'SR',
      color: '#22D3EE',
      metric: '$2M unified view',
    },
  ]

  return (
    <section id="testimonials" className="relative py-24 overflow-hidden">
      <div className="absolute inset-0 grid-bg opacity-25" />
      <div className="glow-orb absolute w-[600px] h-[400px] opacity-8 left-1/2 -translate-x-1/2 top-0" style={{ background: '#3B82F6' }} />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="Customer Stories"
          title="Engineering teams that"
          gradTitle="changed their cloud"
          subtitle="From startup scale-ups to Fortune 500 FinOps teams — real results, real numbers."
        />

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {items.map((t, i) => (
            <div
              key={t.name}
              className="card-hover glass rounded-3xl p-7 flex flex-col cursor-default"
              style={{ border: `1px solid ${t.color}18`, animationDelay: `${i * 0.15}s` }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = t.color + '40'; (e.currentTarget as HTMLElement).style.boxShadow = `0 8px 60px ${t.color}15` }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = t.color + '18'; (e.currentTarget as HTMLElement).style.boxShadow = '' }}
            >
              {/* Stars */}
              <div className="flex gap-1 mb-5">
                {[1,2,3,4,5].map(s => (
                  <svg key={s} viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="#F59E0B"><polygon points="8 1 10.09 5.5 15 6.27 11.5 9.64 12.18 14.5 8 12.18 3.82 14.5 4.5 9.64 1 6.27 5.91 5.5"/></svg>
                ))}
              </div>

              <blockquote className="text-sm text-slate-400 leading-relaxed flex-1 mb-6">
                "{t.quote}"
              </blockquote>

              <div className="border-t pt-5" style={{ borderColor: `${t.color}15` }}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0" style={{ background: `linear-gradient(135deg, ${t.color}60, ${t.color}30)`, border: `1px solid ${t.color}30` }}>
                      {t.avatar}
                    </div>
                    <div>
                      <p className="text-sm font-bold text-white">{t.name}</p>
                      <p className="text-xs text-slate-500">{t.role} · {t.company}</p>
                    </div>
                  </div>
                  <div className="text-xs font-bold font-mono px-2.5 py-1 rounded-lg" style={{ background: `${t.color}12`, color: t.color, border: `1px solid ${t.color}20` }}>
                    {t.metric}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════
   PRICING
═══════════════════════════════════════════════════════════════ */
function Pricing() {
  const [annual, setAnnual] = useState(true)

  const plans = [
    {
      name: 'Starter',
      desc: 'For small teams exploring cloud cost optimization.',
      mo: 199, yr: 149,
      featured: false,
      color: '#22D3EE',
      features: ['Up to $50k/mo cloud spend','1 cloud provider','AI recommendations','Weekly report digest','Email support','14-day free trial'],
    },
    {
      name: 'Pro',
      desc: 'For growing teams with multi-cloud needs and real savings goals.',
      mo: 599, yr: 449,
      featured: true,
      color: '#3B82F6',
      features: ['Up to $500k/mo cloud spend','All 3 cloud providers','One-click optimization','Commitment Manager','Slack + webhook alerts','Priority Slack support'],
    },
    {
      name: 'Enterprise',
      desc: 'Custom solutions for large organizations at scale.',
      mo: null, yr: null,
      featured: false,
      color: '#8B5CF6',
      features: ['Unlimited cloud spend','Custom integrations','SSO & SCIM provisioning','Dedicated CSM','99.9% SLA uptime','Security review & BAA'],
    },
  ]

  return (
    <section id="pricing" className="relative py-24 overflow-hidden">
      <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, #050816 0%, #0a0f2e 50%, #050816 100%)' }} />
      <div className="absolute inset-0 aurora-section opacity-50" />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="Pricing"
          title="Invest less than you"
          gradTitle="save every month"
          subtitle="Every plan pays for itself in the first week. Cancel anytime — we win by keeping you, not locking you in."
        />

        {/* Toggle */}
        <div className="flex items-center justify-center mb-12">
          <div className="inline-flex items-center p-1 rounded-2xl" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
            {['Monthly','Annual'].map((opt) => (
              <button
                key={opt}
                onClick={() => setAnnual(opt === 'Annual')}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200"
                style={{
                  background: (annual ? opt === 'Annual' : opt === 'Monthly') ? 'rgba(59,130,246,0.2)' : 'transparent',
                  color: (annual ? opt === 'Annual' : opt === 'Monthly') ? '#3B82F6' : '#64748b',
                  border: (annual ? opt === 'Annual' : opt === 'Monthly') ? '1px solid rgba(59,130,246,0.3)' : '1px solid transparent',
                }}
              >
                {opt}
                {opt === 'Annual' && <span className="text-[10px] font-bold bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded-full border border-emerald-500/20">−25%</span>}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={`rounded-3xl p-8 relative flex flex-col card-hover ${plan.featured ? 'pricing-featured scale-[1.03]' : 'glass'}`}
              style={!plan.featured ? { border: `1px solid ${plan.color}20` } : {}}
            >
              {plan.featured && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 text-[11px] font-black text-white px-4 py-1.5 rounded-full uppercase tracking-widest" style={{ background: 'linear-gradient(135deg, #3B82F6, #8B5CF6)', boxShadow: '0 0 20px rgba(59,130,246,0.5)' }}>
                  Most Popular
                </div>
              )}

              <p className="text-xs font-mono uppercase tracking-widest mb-1" style={{ color: plan.color }}>{plan.name}</p>
              <p className="text-xs text-slate-500 mb-6">{plan.desc}</p>

              {plan.mo ? (
                <div className="mb-7">
                  <div className="flex items-baseline gap-1">
                    <span className="text-5xl font-black font-display text-white">${annual ? plan.yr : plan.mo}</span>
                    <span className="text-slate-500 text-sm">/mo</span>
                  </div>
                  {annual && <p className="text-xs text-slate-600 mt-1 font-mono">Billed annually · ${((annual ? plan.yr : plan.mo)! * 12).toLocaleString()}/yr</p>}
                </div>
              ) : (
                <div className="mb-7">
                  <p className="text-4xl font-black font-display text-white">Custom</p>
                  <p className="text-xs text-slate-600 mt-1 font-mono">Contact our sales team</p>
                </div>
              )}

              <a
                href="#"
                className="block text-center text-sm font-bold py-3.5 rounded-2xl mb-7 transition-all"
                style={plan.featured
                  ? { background: 'linear-gradient(135deg, #3B82F6, #22D3EE)', color: 'white', boxShadow: '0 0 30px rgba(59,130,246,0.3)' }
                  : { background: `${plan.color}10`, color: plan.color, border: `1px solid ${plan.color}30` }
                }
              >
                {plan.name === 'Enterprise' ? 'Contact Sales' : 'Start Free Trial'}
              </a>

              <div className="space-y-3">
                {plan.features.map(f => (
                  <div key={f} className="flex items-center gap-3">
                    <div className="w-4 h-4 rounded-full flex items-center justify-center shrink-0" style={{ background: `${plan.color}20` }}>
                      <svg viewBox="0 0 10 10" className="w-2.5 h-2.5"><polyline points="2 5 4 7 8 3" stroke={plan.color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/></svg>
                    </div>
                    <span className="text-xs text-slate-400">{f}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════
   FAQ
═══════════════════════════════════════════════════════════════ */
function FAQ() {
  const [open, setOpen] = useState<number | null>(0)

  const faqs = [
    { q: 'How quickly will I see results after connecting my cloud accounts?', a: 'Most customers receive their first AI recommendations within 30 minutes of connecting an account. The more historical data available (we analyze up to 13 months), the more accurate and comprehensive the recommendations become.' },
    { q: 'Does CloudWise make any changes to my infrastructure automatically?', a: 'No. CloudWise is entirely read-only by default. Every recommended change is presented to your team for review and requires explicit approval. You remain in complete control at all times, and every action is audited.' },
    { q: 'Is my billing data and cloud credentials secure?', a: 'Yes. CloudWise is SOC 2 Type II certified and GDPR compliant. We use short-lived, read-only IAM roles with the minimum permissions required. Your data is encrypted at rest (AES-256) and in transit (TLS 1.3). We never store long-lived credentials.' },
    { q: 'What cloud providers do you support?', a: 'CloudWise natively supports AWS, Microsoft Azure, and Google Cloud Platform — covering over 530 resource types including compute, storage, databases, networking, and managed AI/ML services.' },
    { q: 'How does CloudWise compare to native tools like AWS Cost Explorer?', a: 'Native tools show you what you\'ve spent. CloudWise tells you what to do about it. Our AI engine goes beyond visibility to generate a prioritized action queue with projected savings for every recommendation — something no native tool provides across all three clouds simultaneously.' },
    { q: 'Can I try CloudWise without a credit card?', a: 'Absolutely. Our 14-day free trial includes full access to all Starter features with no credit card required. You can connect up to one cloud provider and receive your first recommendations in under an hour.' },
  ]

  return (
    <section id="faq" className="relative py-24 overflow-hidden">
      <div className="absolute inset-0 grid-bg opacity-20" />
      <div className="relative max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="FAQ"
          title="Everything you need"
          gradTitle="to know"
          subtitle="Clear answers to the questions engineering and FinOps teams ask before signing up."
        />

        <div className="space-y-2">
          {faqs.map((faq, i) => (
            <div
              key={i}
              className="rounded-2xl overflow-hidden transition-all duration-200"
              style={{ border: `1px solid ${open === i ? 'rgba(59,130,246,0.3)' : 'rgba(255,255,255,0.05)'}`, background: open === i ? 'rgba(59,130,246,0.05)' : 'rgba(255,255,255,0.02)' }}
            >
              <button
                onClick={() => setOpen(open === i ? null : i)}
                className="w-full flex items-center justify-between px-6 py-5 text-left"
              >
                <span className="text-sm font-semibold text-white pr-6 leading-snug">{faq.q}</span>
                <svg viewBox="0 0 20 20" className="w-4 h-4 text-blue-400 shrink-0 transition-transform duration-200" style={{ transform: open === i ? 'rotate(180deg)' : 'rotate(0)' }} fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="5 8 10 13 15 8" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
              <div className="faq-body" style={{ maxHeight: open === i ? '300px' : '0', opacity: open === i ? 1 : 0 }}>
                <div className="px-6 pb-5">
                  <p className="text-sm text-slate-400 leading-relaxed">{faq.a}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════
   CTA
═══════════════════════════════════════════════════════════════ */
function CTA() {
  return (
    <section className="relative py-24 overflow-hidden">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="relative rounded-[2.5rem] overflow-hidden">
          {/* Bg */}
          <div className="absolute inset-0" style={{ background: 'linear-gradient(135deg, #0a0f2e 0%, #050816 50%, #0f0a2e 100%)' }} />
          <div className="absolute inset-0 grid-bg opacity-40" />
          <div className="glow-orb absolute w-[600px] h-[400px] opacity-20 -left-20 top-1/2 -translate-y-1/2" style={{ background: '#3B82F6', animation: 'aurora-shift 8s ease-in-out infinite' }} />
          <div className="glow-orb absolute w-[400px] h-[400px] opacity-15 -right-20 top-1/2 -translate-y-1/2" style={{ background: '#8B5CF6', animation: 'aurora-shift 10s ease-in-out infinite reverse' }} />
          {/* Top line */}
          <div className="absolute top-0 inset-x-0 h-px" style={{ background: 'linear-gradient(90deg, transparent, rgba(59,130,246,0.7), rgba(139,92,246,0.5), transparent)' }} />
          {/* Bottom line */}
          <div className="absolute bottom-0 inset-x-0 h-px" style={{ background: 'linear-gradient(90deg, transparent, rgba(34,211,238,0.4), rgba(59,130,246,0.5), transparent)' }} />

          <div className="relative z-10 px-8 sm:px-16 py-20 text-center">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 glass-blue rounded-full px-5 py-2 mb-8 badge-glow">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse-glow" />
              <span className="text-xs font-mono font-semibold text-cyan-300 uppercase tracking-widest">$140M+ Saved by CloudWise Teams</span>
            </div>

            <h2 className="text-5xl sm:text-6xl lg:text-7xl font-black text-white font-display tracking-tight mb-6 leading-[1.02]">
              Your cloud is spending
              <br />
              <span className="grad-blue-cyan text-glow-blue">money right now.</span>
            </h2>

            <p className="text-slate-400 text-xl max-w-2xl mx-auto mb-10 leading-relaxed">
              Join 2,400+ engineering teams who've cut cloud bills with CloudWise.
              First AI recommendations in under 30 minutes. No credit card required.
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <a href="#" className="btn-primary group inline-flex items-center gap-2 text-base font-bold text-white px-8 py-4 rounded-2xl">
                Start Free Trial — No Card Needed
                <svg viewBox="0 0 20 20" className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="4" y1="10" x2="16" y2="10" strokeLinecap="round"/>
                  <polyline points="10 4 16 10 10 16" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </a>
              <a href="#" className="btn-outline inline-flex items-center gap-2 text-base font-semibold text-slate-300 hover:text-white px-8 py-4 rounded-2xl">
                Book a Live Demo
              </a>
            </div>

            <p className="text-slate-600 text-sm mt-6 font-mono">14-day free trial · No credit card · Cancel anytime · SOC 2 Type II</p>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════
   FOOTER
═══════════════════════════════════════════════════════════════ */
function Footer() {
  const columns = [
    { heading: 'Product', links: ['Features', 'How It Works', 'Pricing', 'Changelog', 'Roadmap'] },
    { heading: 'Solutions', links: ['AWS Optimization', 'Azure Cost Control', 'GCP Savings', 'FinOps Teams', 'Startups'] },
    { heading: 'Company', links: ['About', 'Blog', 'Careers', 'Press Kit', 'Contact'] },
    { heading: 'Legal', links: ['Privacy Policy', 'Terms of Service', 'Security', 'Cookie Policy', 'GDPR'] },
  ]

  return (
    <footer style={{ background: '#030711', borderTop: '1px solid rgba(59,130,246,0.1)' }}>
      {/* Top accent line */}
      <div className="h-px" style={{ background: 'linear-gradient(90deg, transparent, rgba(59,130,246,0.4), rgba(139,92,246,0.3), rgba(34,211,238,0.2), transparent)' }} />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-8">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-10 mb-14">
          {/* Brand */}
          <div className="md:col-span-1">
            <div className="flex items-center gap-2.5 mb-4">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'linear-gradient(135deg,#3B82F6,#22D3EE)', boxShadow: '0 0 20px rgba(59,130,246,0.4)' }}>
                <svg viewBox="0 0 20 20" className="w-4 h-4" fill="none"><path d="M17 10a5 5 0 0 0-4.9-5A4.5 4.5 0 0 0 3.5 8.5 3.5 3.5 0 0 0 5 15h12a3 3 0 0 0 0-6z" stroke="white" strokeWidth="1.5" strokeLinejoin="round"/></svg>
              </div>
              <span className="text-lg font-bold font-display text-white tracking-tight">
                Cloud<span className="grad-blue-cyan">Wise</span>
              </span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed mb-5">
              AI-powered cloud cost optimization for modern engineering teams across AWS, Azure, and GCP.
            </p>
            <div className="flex items-center gap-2.5">
              {[
                <path key="tw" d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />,
                <path key="li" d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6zM2 9h4v12H2z M4 4m-2 0a2 2 0 0 1 4 0 2 2 0 0 1-4 0" />,
                <path key="gh" d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />,
              ].map((iconPath, i) => (
                <a key={i} href="#" className="w-8 h-8 rounded-xl flex items-center justify-center transition-all" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(59,130,246,0.12)'; (e.currentTarget as HTMLElement).style.borderColor = 'rgba(59,130,246,0.3)' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.04)'; (e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,255,255,0.06)' }}>
                  <svg viewBox="0 0 24 24" className="w-3.5 h-3.5 text-slate-500" fill="currentColor"><path d={typeof iconPath.props.d === 'string' ? iconPath.props.d : ''} /></svg>
                </a>
              ))}
            </div>
          </div>

          {/* Link columns */}
          {columns.map(col => (
            <div key={col.heading}>
              <p className="text-xs font-bold text-slate-300 uppercase tracking-widest mb-5 font-mono">{col.heading}</p>
              <ul className="space-y-3">
                {col.links.map(link => (
                  <li key={link}>
                    <a href="#" className="text-xs text-slate-600 hover:text-slate-400 transition-colors">{link}</a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-8" style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
          <p className="text-xs text-slate-700 font-mono">© 2026 CloudWise, Inc. All rights reserved.</p>
          <div className="flex items-center gap-4 text-xs text-slate-700 font-mono">
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-glow" />
              <span>All systems operational</span>
            </div>
            <span className="text-slate-800">·</span>
            <span>SOC 2 Type II</span>
            <span className="text-slate-800">·</span>
            <span>GDPR Compliant</span>
          </div>
        </div>
      </div>
    </footer>
  )
}

/* ═══════════════════════════════════════════════════════════════
   APP
═══════════════════════════════════════════════════════════════ */
export default function App() {
  return (
    <div style={{ background: '#050816' }}>
      <Navbar />
      <main>
        <Hero />
        <TrustedBy />
        <CloudProviders />
        <Features />
        <HowItWorks />
        <AIRecommendationPreview />
        <DashboardPreview />
        <Testimonials />
        <Pricing />
        <FAQ />
        <CTA />
      </main>
      <Footer />
    </div>
  )
}
