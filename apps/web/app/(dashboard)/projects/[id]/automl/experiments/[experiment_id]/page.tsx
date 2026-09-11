import ClientPage from "./client";

export function generateStaticParams() { return [{ id: 'default', experiment_id: 'default' }]; }

export default function Page() {
  return <ClientPage />;
}
