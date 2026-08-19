import React from "react"
import { Link, useLocation } from "react-router-dom"
import { motion } from "framer-motion"
import { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

export interface NavItem {
  name: string
  url: string
  icon: LucideIcon
}

export interface NavBarProps {
  items: NavItem[]
  className?: string
}

export function NavBar({ items, className }: NavBarProps) {
  const location = useLocation()

  return (
    <nav
      aria-label="Main Navigation"
      className={cn(
        "fixed bottom-6 left-1/2 -translate-x-1/2 z-50 max-w-[96vw] sm:max-w-none",
        className,
      )}
    >
      <div className="flex items-center gap-0.5 sm:gap-1.5 bg-slate-950/85 border border-slate-800/80 backdrop-blur-xl py-1.5 px-2 rounded-full shadow-2xl shadow-cyan-950/50">
        {items.map((item) => {
          const Icon = item.icon
          // Handle root route accurately vs sub-routes
          const isActive =
            item.url === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(item.url)

          return (
            <Link
              key={item.name}
              to={item.url}
              title={item.name}
              className={cn(
                "relative cursor-pointer text-xs sm:text-sm font-medium px-2.5 sm:px-4 py-1.5 sm:py-2 rounded-full transition-all duration-200 flex items-center gap-2 select-none",
                "text-slate-400 hover:text-cyan-300",
                isActive && "text-cyan-300 font-semibold shadow-inner",
              )}
            >
              <Icon
                size={18}
                strokeWidth={isActive ? 2.5 : 2}
                className={cn(
                  "transition-all duration-200",
                  isActive ? "text-cyan-400 scale-110" : "text-slate-400 group-hover:text-cyan-300"
                )}
              />
              
              {/* Show text on desktop */}
              <span className="hidden md:inline whitespace-nowrap">{item.name}</span>

              {/* Tubelight Glow Lamp Effect */}
              {isActive && (
                <motion.div
                  layoutId="lamp"
                  className="absolute inset-0 w-full bg-cyan-500/10 rounded-full -z-10 border border-cyan-500/25"
                  initial={false}
                  transition={{
                    type: "spring",
                    stiffness: 320,
                    damping: 28,
                  }}
                >
                  {/* Glowing Top Line / Beam */}
                  <div className="absolute -top-2 left-1/2 -translate-x-1/2 w-8 h-1 bg-cyan-400 rounded-t-full shadow-[0_-4px_14px_rgba(6,182,212,0.9)]">
                    <div className="absolute w-12 h-6 bg-cyan-400/30 rounded-full blur-md -top-2 -left-2" />
                    <div className="absolute w-8 h-6 bg-cyan-400/25 rounded-full blur-md -top-1" />
                    <div className="absolute w-4 h-4 bg-cyan-400/40 rounded-full blur-sm top-0 left-2" />
                  </div>
                </motion.div>
              )}
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
