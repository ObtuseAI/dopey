
export const PageHeader = ({
  index,
  title,
  thesis,
  timestamp,
  timestampText,
}: {
  readonly index: string;
  readonly title: string;
  readonly thesis: string;
  readonly timestamp: string | null;
  readonly timestampText: string;
}) => (
  <header className="view-header">
    <div className="view-header__index">{index}</div>
    <div>
      <span className="eyebrow">DOPEY / OPERATOR SURFACE</span>
      <h1>{title}</h1>
      <p>{thesis}</p>
    </div>
    <time dateTime={timestamp ?? ""} title={timestamp ?? "Timestamp not reported"}>{timestampText}</time>
  </header>
);
