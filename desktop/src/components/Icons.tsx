import type { ReactNode } from "react";

interface IconProps {
  readonly children: ReactNode;
  readonly size: number;
  readonly label: string | null;
}

const IconFrame = ({ children, size, label }: IconProps) => (
  <svg
    aria-hidden={label === null}
    aria-label={label ?? undefined}
    className="icon"
    fill="none"
    height={size}
    role={label === null ? undefined : "img"}
    stroke="currentColor"
    strokeLinecap="square"
    strokeLinejoin="miter"
    strokeWidth="1.5"
    viewBox="0 0 24 24"
    width={size}
  >
    {children}
  </svg>
);

export const CommandIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M4 17V7h4l2 4 3-7 3 13 2-6h2" />
  </IconFrame>
);

export const TissueIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" />
    <path d="M10 7h4M7 10v4M17 10v4M10 17h4" />
  </IconFrame>
);

export const ChartIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M3 4v16h18" />
    <path d="M6 15V9M5 11h2M10 17V7M9 14h2M14 13V4M13 7h2M18 18V10M17 12h2" />
  </IconFrame>
);

export const LabIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3" />
    <path d="M7 16h10M9 13h6" />
  </IconFrame>
);

export const PlaybookIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M4 18l5-5 3 3 7-9" />
    <path d="M14 7h5v5M4 6h6M4 10h4" />
  </IconFrame>
);

export const OrganismIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M12 3v18M12 6l-5 3v6l5 3M12 6l5 3v6l-5 3M7 9l5 3 5-3M7 15l5-3 5 3" />
  </IconFrame>
);

export const TruthIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M4 5h16v14H4zM7 15l3-3 2 2 5-6" />
  </IconFrame>
);

export const EvidenceIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M4 18V6h4v12zM10 14V9h4v5zM16 20V3h4v17z" />
    <path d="M3 20h18M6 4l6 3 6-5" />
  </IconFrame>
);

export const EvolutionIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M5 19V5h5v5h4V5h5v14h-5v-5h-4v5z" />
  </IconFrame>
);

export const BookIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M4 5h6c2 0 2 2 2 2s0-2 2-2h6v14h-6c-2 0-2 2-2 2s0-2-2-2H4zM12 7v14" />
  </IconFrame>
);

export const ConstitutionIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M12 3l8 4v5c0 5-3 8-8 9-5-1-8-4-8-9V7zM8 12l3 3 5-6" />
  </IconFrame>
);

export const RefreshIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M19 8V4l-2 2a8 8 0 1 0 2 10M19 4h-4" />
  </IconFrame>
);

export const SearchIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="m15.5 15.5 4.5 4.5" />
  </IconFrame>
);

export const MinimizeIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M6 12h12" />
  </IconFrame>
);

export const MaximizeIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M6 6h12v12H6z" />
  </IconFrame>
);

export const CloseIcon = ({ size }: { readonly size: number }) => (
  <IconFrame label={null} size={size}>
    <path d="M6 6l12 12M18 6L6 18" />
  </IconFrame>
);
