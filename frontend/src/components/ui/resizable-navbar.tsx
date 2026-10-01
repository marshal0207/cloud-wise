import { IconMenu2, IconX } from '@tabler/icons-react';
import {
  AnimatePresence,
  motion,
  useMotionValueEvent,
  useScroll,
} from 'motion/react';
import React, { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';

interface NavbarProps {
  children: React.ReactNode;
  className?: string;
}

interface NavBodyProps {
  children: React.ReactNode;
  className?: string;
  visible?: boolean;
}

interface NavItemsProps {
  items: { name: string; link: string }[];
  className?: string;
  onItemClick?: () => void;
  activePath?: string;
}

interface MobileNavProps {
  children: React.ReactNode;
  className?: string;
  visible?: boolean;
}

interface MobileNavHeaderProps {
  children: React.ReactNode;
  className?: string;
}

interface MobileNavMenuProps {
  children: React.ReactNode;
  className?: string;
  isOpen: boolean;
  onClose: () => void;
}

export const Navbar = ({ children, className }: NavbarProps) => {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollY } = useScroll({
    target: ref,
    offset: ['start start', 'end start'],
  });
  const [visible, setVisible] = useState(false);

  useMotionValueEvent(scrollY, 'change', (latest) => {
    setVisible(latest > 100);
  });

  return (
    <motion.div
      ref={ref}
      className={cn('sticky inset-x-0 top-20 z-40 w-full', className)}
    >
      {React.Children.map(children, (child) =>
        React.isValidElement(child)
          ? React.cloneElement(
              child as React.ReactElement<{ visible?: boolean }>,
              { visible },
            )
          : child,
      )}
    </motion.div>
  );
};

export const NavBody = ({ children, className, visible }: NavBodyProps) => (
  <motion.div
    animate={{
      backdropFilter: visible ? 'blur(10px)' : 'none',
      boxShadow: visible
        ? '0 0 24px rgba(34, 42, 53, 0.06), 0 1px 1px rgba(0, 0, 0, 0.05), 0 0 0 1px rgba(34, 42, 53, 0.04), 0 0 4px rgba(34, 42, 53, 0.08), 0 16px 68px rgba(47, 48, 55, 0.05), 0 1px 0 rgba(255, 255, 255, 0.1) inset'
        : 'none',
      width: '100%',
      y: visible ? 8 : 0,
    }}
    transition={{ type: 'spring', stiffness: 200, damping: 50 }}
    className={cn(
      'relative z-[60] mx-auto hidden w-full max-w-7xl flex-row items-center justify-between self-start rounded-full border border-white/10 bg-black/60 px-5 py-2 shadow-2xl xl:flex',
      visible && 'bg-black/75',
      className,
    )}
  >
    {children}
  </motion.div>
);

export const NavItems = ({ items, className, onItemClick, activePath }: NavItemsProps) => {
  const [hovered, setHovered] = useState<number | null>(null);

  return (
    <motion.div
      onMouseLeave={() => setHovered(null)}
      className={cn(
        'relative z-10 flex min-w-0 flex-1 flex-row items-center justify-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400 transition duration-200',
        className,
      )}
    >
      {items.map((item, index) => (
        <Link
          key={`link-${index}`}
          to={item.link}
          onMouseEnter={() => setHovered(index)}
          onClick={onItemClick}
          className={cn(
            'relative cursor-pointer whitespace-nowrap rounded-full px-2 py-1.5 text-slate-400 transition-colors hover:text-white',
            activePath === item.link && 'bg-white/10 text-white',
          )}
        >
          {hovered === index && (
            <motion.span
              layoutId="cloudwise-navbar-hovered"
              className="absolute inset-0 rounded-full bg-white/5"
            />
          )}
          <span className="relative z-20">{item.name}</span>
        </Link>
      ))}
    </motion.div>
  );
};

export const MobileNav = ({ children, className, visible }: MobileNavProps) => (
  <motion.div
    animate={{
      backdropFilter: visible ? 'blur(10px)' : 'none',
      boxShadow: visible
        ? '0 0 24px rgba(34, 42, 53, 0.06), 0 1px 1px rgba(0, 0, 0, 0.05), 0 0 0 1px rgba(34, 42, 53, 0.04), 0 0 4px rgba(34, 48, 55, 0.08)'
        : 'none',
      width: visible ? '90%' : '100%',
      paddingRight: visible ? 12 : 0,
      paddingLeft: visible ? 12 : 0,
      borderRadius: visible ? 16 : 32,
      y: visible ? 20 : 0,
    }}
    transition={{ type: 'spring', stiffness: 200, damping: 50 }}
    className={cn(
      'relative z-50 mx-auto flex w-full max-w-[calc(100vw-2rem)] flex-col items-center justify-between border border-white/10 bg-black/60 px-0 py-2 shadow-2xl xl:hidden',
      className,
    )}
  >
    {children}
  </motion.div>
);

export const MobileNavHeader = ({ children, className }: MobileNavHeaderProps) => (
  <div className={cn('flex w-full flex-row items-center justify-between', className)}>
    {children}
  </div>
);

export const MobileNavMenu = ({
  children,
  className,
  isOpen,
}: MobileNavMenuProps) => (
  <AnimatePresence>
    {isOpen && (
      <motion.div
        initial={{ opacity: 0, height: 0 }}
        animate={{ opacity: 1, height: 'auto' }}
        exit={{ opacity: 0, height: 0 }}
        className={cn(
          'absolute inset-x-0 top-16 z-50 flex w-full flex-col items-start justify-start gap-2 overflow-hidden rounded-2xl border border-white/10 bg-[#0A0E17]/95 px-4 py-4 shadow-2xl',
          className,
        )}
      >
        {children}
      </motion.div>
    )}
  </AnimatePresence>
);

export const MobileNavToggle = ({
  isOpen,
  onClick,
}: {
  isOpen: boolean;
  onClick: () => void;
}) =>
  isOpen ? (
    <IconX className="cursor-pointer text-slate-300" onClick={onClick} />
  ) : (
    <IconMenu2 className="cursor-pointer text-slate-300" onClick={onClick} />
  );