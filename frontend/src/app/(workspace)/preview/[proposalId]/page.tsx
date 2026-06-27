import Link from "next/link";

import { PageHeader } from "@/components/layout/page-header";
import { PreviewSplit } from "@/components/preview/preview-split";
import { Button } from "@/components/ui/button";

export default async function PreviewPage({
  params,
}: {
  params: Promise<{ proposalId: string }>;
}) {
  const { proposalId } = await params;
  return (
    <>
      <PageHeader
        title="Proposal document"
        subtitle="Edit the proposal in place, then export it to PDF or DOCX."
        actions={
          <Link href="/generate">
            <Button variant="secondary">← Back</Button>
          </Link>
        }
      />
      <PreviewSplit proposalId={proposalId} />
    </>
  );
}
