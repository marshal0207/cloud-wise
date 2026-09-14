import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Link, useLocation } from 'react-router-dom';
import { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface SlideTabItem {
  name: string;
  url: string;
  icon: LucideIcon;
}

interface CursorPosition {
  left: number;
  width: number;
  opacity: number;
}

interface SlideTabsProps {
  items: SlideTabItem[];
  className?: string;
}

export const SlideTabs: React.FC<SlideTabsProps> = ({ items, className }) => {
  const location = useLocation();
  const tabsRef = useRef<Array<HTMLLIElement | null>>([]);
  const containerRef = useRef<HTMLUListElement | null>(null);
  const [position, setPosition] = useState<CursorPosition>({
    left: 0,
    width: 0,
    opacity: 0,
  });

  const selectedIndex = Math.max(
    0,
    items.findIndex((item) =>
      item.url === '/' ? location.pathname === '/' : location.pathname.startsWith(item.url),
    ),
  );

  const updatePosition = (index: number) => {
    const selectedTab = tabsRef.current[index];
    const container = containerRef.current;
    if (!selectedTab || !container) return;

    const tabBounds = selectedTab.getBoundingClientRect();
    const containerBounds = container.getBoundingClientRect();

    setPosition({
      left: tabBounds.left - containerBounds.left,
      width: tabBounds.width,
      opacity: 1,
    });
  };

  useEffect(() => {
    updatePosition(selectedIndex);
  }, [selectedIndex]);

  return (
    <nav
      aria-label="Main Navigation"
      className={cn(
        'fixed bottom-6 left-1/2 z-50 max-w-[96vw] -translate-x-1/2',
        className,
      )}
    >
      <ul
        ref={containerRef}
        onMouseLeave={() => {
          updatePosition(selectedIndex);
        }}
        className="relative flex w-fit max-w-[calc(100vw-1rem)] overflow-x-auto rounded-full border-2 border-slate-700/80 bg-slate-950/90 p-1 shadow-2xl shadow-cyan-950/50 backdrop-blur-xl scrollbar-none"
      >
        {items.map((item, index) => {
          const Icon = item.icon;
          const isActive = index === selectedIndex;

          return (
            <li
              key={item.name}
              ref={(element) => {
                tabsRef.current[index] = element;
              }}
              className="relative z-10 shrink-0"
            >
              <Link
                to={item.url}
                title={item.name}
                onMouseEnter={() => {
                  updatePosition(index);
                }}
                className={cn(
                  'relative flex cursor-pointer items-center gap-1.5 rounded-full px-2 py-1.5 text-xs font-medium transition-colors sm:gap-2 sm:px-3 sm:py-2 sm:text-sm',
                  isActive ? 'text-white' : 'text-slate-400 hover:text-white',
                )}
              >
                <Icon size={16} strokeWidth={isActive ? 2.5 : 2} />
                <span className="hidden whitespace-nowrap md:inline">{item.name}</span>
              </Link>
            </li>
          );
        })}

        <motion.li
          aria-hidden="true"
          animate={position}
          transition={{ type: 'spring', stiffness: 320, damping: 28 }}
          className="pointer-events-none absolute inset-y-1 z-0 rounded-full bg-cyan-400 shadow-[0_0_18px_rgba(34,211,238,0.45)]"
        />
      </ul>
    </nav>
  );
};