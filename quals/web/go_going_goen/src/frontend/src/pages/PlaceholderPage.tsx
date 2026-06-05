import type { JSX } from "react";

type PlaceholderPageProps = {
  title: string;
};

export const PlaceholderPage = ({ title }: PlaceholderPageProps): JSX.Element => {
  return (
    <section className="placeholder">
      <h2>{title}</h2>
      <p>This page is scaffolded and ready for its workstream.</p>
    </section>
  );
};
