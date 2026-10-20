import { FixAttemptView } from "@/components/FixAttemptView";

export default async function FixPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <FixAttemptView id={Number(id)} />;
}
