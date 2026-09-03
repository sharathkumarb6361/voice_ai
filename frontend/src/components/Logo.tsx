import React, { useState } from 'react';
import logoImg from '../assets/logo.jpg';

interface LogoProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const Logo: React.FC<LogoProps> = ({ className = '', size = 'md' }) => {
  const [imageError, setImageError] = useState(false);

  const sizeClasses = {
    sm: 'w-8 h-8 rounded-lg',
    md: 'w-10 h-10 sm:w-11 sm:h-11 rounded-xl',
    lg: 'w-16 h-16 rounded-2xl'
  }[size];

  const iconSizes = {
    sm: 'text-sm',
    md: 'text-base sm:text-lg',
    lg: 'text-2xl'
  }[size];

  return (
    <div className={`flex-shrink-0 relative ${sizeClasses} flex items-center justify-center ${className}`}>
      {!imageError ? (
        <img
          src={logoImg || '/logo.jpg'}
          alt="VoiceAssistant.ai Logo"
          onError={(e) => {
            if (!e.currentTarget.src.endsWith('/logo.jpg')) {
              e.currentTarget.src = '/logo.jpg';
            } else {
              setImageError(true);
            }
          }}
          className={`w-full h-full ${sizeClasses} object-cover border border-indigo-400/50 shadow-md group-hover:scale-105 transition-transform bg-slate-900`}
        />
      ) : (
        <div className={`w-full h-full ${sizeClasses} bg-gradient-to-br from-indigo-600 via-purple-600 to-blue-700 border border-indigo-400/50 shadow-md flex items-center justify-center text-white group-hover:scale-105 transition-transform`}>
          <i className={`fa-solid fa-microphone-lines ${iconSizes} text-amber-300`} />
        </div>
      )}
    </div>
  );
};
