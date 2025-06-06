import React, { memo, useState, useEffect } from "react";
import { Loader2, Maximize2, Minimize2, X } from "lucide-react";
import { createPortal } from "react-dom";

export const LoadingIndicator = ({ size = 16 }: { size: number }) => (
  // 旋转加载图标
  <div className="inline-flex items-center gap-2 text-accent   mr-2">
    <Loader2 size={size} className="animate-spin" />
  </div>
);

export const LoadingDots = ({ size = 8 }) => {
  // 三个点的加载动画
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className="bg-accent rounded-full animate-bounce"
        style={{
          width: `${size}px`,
          height: `${size}px`,
          animationDuration: "0.6s",
        }}
      />
      <span
        className="bg-accent rounded-full animate-bounce"
        style={{
          width: `${size}px`,
          height: `${size}px`,
          animationDuration: "0.6s",
          animationDelay: "0.2s",
        }}
      />
      <span
        className="bg-accent rounded-full animate-bounce"
        style={{
          width: `${size}px`,
          height: `${size}px`,
          animationDuration: "0.6s",
          animationDelay: "0.4s",
        }}
      />
    </span>
  );
};

export const TruncatableText = memo(
  ({
    content,
    isJson = false,
    className = "",
    jsonThreshold = 1000,
    textThreshold = 500,
  }: {
    content: string;
    isJson?: boolean;
    className?: string;
    jsonThreshold?: number;
    textThreshold?: number;
  }) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const threshold = isJson ? jsonThreshold : textThreshold;
    const shouldTruncate = content.length > threshold;

    const toggleExpand = () => {
      setIsExpanded(!isExpanded);
    };

    const displayContent =
      shouldTruncate && !isExpanded
        ? content.slice(0, threshold) + "..."
        : content;

    return (
      <div className="relative">
        <div
          className={`
            transition-[max-height,opacity] duration-500 ease-in-out
            ${
              shouldTruncate && !isExpanded
                ? "max-h-[300px]"
                : "max-h-[10000px]"
            }
            ${className}
          `}
        >
          {displayContent}
          {shouldTruncate && !isExpanded && (
            <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-secondary/20 to-transparent" />
          )}
        </div>

        {shouldTruncate && (
          <div className="mt-2 flex items-center justify-end">
            <button
              type="button"
              onClick={toggleExpand}
              className={`
                inline-flex items-center gap-2 px-3 py-1.5 
                rounded bg-secondary/80 
                text-xs font-medium
                transition-all duration-300
                 hover:text-accent
                hover:scale-105
                z-10
              `}
              aria-label={isExpanded ? "less" : "more"}
            >
              <span>{isExpanded ? "Show less" : "Show more"}</span>
              {isExpanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
          </div>
        )}
      </div>
    );
  }
);

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
}

const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  children,
  className = "",
}) => {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";

      const handleEscape = (e: KeyboardEvent) => {
        if (e.key === "Escape") onClose();
      };
      window.addEventListener("keydown", handleEscape);
      return () => {
        document.body.style.overflow = "";
        window.removeEventListener("keydown", handleEscape);
      };
    }
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50"
      aria-modal="true"
      role="dialog"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" />
      <div
        className={`
        relative z-10 
        w-full h-full
        flex items-center justify-center
        ${className}
      `}
      >
        {children}
      </div>
    </div>,
    document.body
  );
};

const FullScreenImage: React.FC<{
  src: string;
  alt: string;
  onClose: () => void;
  className?: string;
}> = ({ src, alt, onClose, className = "" }) => {
  return (
    <Modal isOpen={true} onClose={onClose}>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
        className="absolute top-4 right-4 p-2 rounded-full bg-black/50 hover:bg-black/70 text-white transition-all duration-300 hover:scale-105"
        aria-label="Close fullscreen image"
      >
        <X size={24} />
      </button>
      <div className="relative" onClick={(e) => e.stopPropagation()}>
        <img
          src={src}
          alt={alt}
          className={`
            max-h-[90vh] max-w-[90vw] 
            object-contain rounded-lg 
            shadow-2xl
            ${className}
          `}
        />
      </div>
    </Modal>
  );
};

export const ClickableImage: React.FC<{
  src: string;
  alt: string;
  className?: string;
  expandedClassName?: string;
}> = ({ src, alt, className = "", expandedClassName = "" }) => {
  const [isFullScreen, setIsFullScreen] = useState(false);

  return (
    <>
      <img
        src={src}
        alt={alt}
        className={`
          ${className} 
          cursor-zoom-in 
          transition-all duration-300 
          hover:brightness-110
        `}
        onClick={() => setIsFullScreen(true)}
      />
      {isFullScreen && (
        <FullScreenImage
          src={src}
          alt={alt}
          className={expandedClassName}
          onClose={() => setIsFullScreen(false)}
        />
      )}
    </>
  );
};

// dateUtils.ts
export function getRelativeTimeString(date: string | number | Date): string {
  const now = new Date();
  const past = new Date(date);
  const diffInMs = now.getTime() - past.getTime();

  const diffInSeconds = Math.floor(diffInMs / 1000);
  const diffInMinutes = Math.floor(diffInSeconds / 60);
  const diffInHours = Math.floor(diffInMinutes / 60);
  const diffInDays = Math.floor(diffInHours / 24);
  const diffInMonths = Math.floor(diffInDays / 30);
  const diffInYears = Math.floor(diffInDays / 365);

  if (diffInSeconds < 60) {
    return "just now";
  } else if (diffInMinutes < 60) {
    return `${diffInMinutes} ${diffInMinutes === 1 ? "minute" : "minutes"} ago`;
  } else if (diffInHours < 24) {
    return `${diffInHours} ${diffInHours === 1 ? "hour" : "hours"} ago`;
  } else if (diffInDays < 30) {
    return `${diffInDays} ${diffInDays === 1 ? "day" : "days"} ago`;
  } else if (diffInMonths < 12) {
    return `${diffInMonths} ${diffInMonths === 1 ? "month" : "months"} ago`;
  } else {
    return `${diffInYears} ${diffInYears === 1 ? "year" : "years"} ago`;
  }
}
