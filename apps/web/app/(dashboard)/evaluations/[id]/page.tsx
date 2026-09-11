import ClientPage from "./client";

export function generateStaticParams() { return [{ id: 'default' }]; }

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  return <ClientPage params={params} />;
}
