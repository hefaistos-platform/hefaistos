import React from 'react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  title: string;
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '4xl' | '5xl' | 'full';
  disableClose?: boolean;
}

const sizeClasses: Record<NonNullable<ModalProps['size']>, string> = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
  '4xl': 'max-w-4xl',
  '5xl': 'max-w-5xl',
  full: 'max-w-full mx-4',
};

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  size = 'lg',
  disableClose = false,
}) => {
  if (!isOpen) {
    return null;
  }

  return (
    // --- Overlay ---
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
      onClick={() => {
        if (!disableClose) onClose();
      }} // Close when clicking the overlay
    >
      {/* --- Content Box --- */}
      <div
        className={`w-full ${sizeClasses[size]} p-6 border-2 border-hefaistos-border rounded-lg max-h-[90vh] overflow-y-auto`}
        style={{
          background: 'var(--hef-bg-surface)',
          borderColor: 'var(--hef-border)',
          color: 'var(--hef-text-primary)',
          boxShadow: 'var(--hef-shadow-card)',
        }}
        onClick={(e) => e.stopPropagation()} // Prevent closing when clicking inside
      >
        {/* --- Modal Header --- */}
        <div className="flex justify-between items-center pb-4 border-b-2 border-hefaistos-border" style={{ borderColor: 'var(--hef-border)' }}>
          <h3 className="text-2xl font-bold">{title}</h3>
          <button 
            onClick={() => {
              if (!disableClose) onClose();
            }}
            disabled={disableClose}
            className={`${disableClose ? 'cursor-not-allowed opacity-50' : ''}`}
            style={{ color: 'var(--hef-text-muted)' }}
          >
            {/* A simple 'X' for close */}
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
          </button>
        </div>

        {/* --- Modal Body --- */}
        <div className="mt-4">
          {children}
        </div>
      </div>
    </div>
  );
};
