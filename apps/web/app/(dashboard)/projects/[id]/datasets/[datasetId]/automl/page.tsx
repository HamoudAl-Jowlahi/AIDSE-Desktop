import ClientPage from "./client";

export function generateStaticParams() { return [{ id: 'default', datasetId: 'default' }]; }

export default function Page() {
  return <ClientPage />;
}
