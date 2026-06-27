import { GenerateForm } from "@/components/generation/generate-form";
import { PageHeader } from "@/components/layout/page-header";

export default function GeneratePage() {
  return (
    <>
      <PageHeader
        title="Generate proposal"
        subtitle="Federated retrieval across financial evidence, exemplars, and templates — grounded, cited, and guardrailed."
      />
      <GenerateForm />
    </>
  );
}
