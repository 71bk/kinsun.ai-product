import { AssignmentWorkbench } from '@/components/care/AssignmentWorkbench';

export default async function AssignmentPage({
  params,
}: {
  params: Promise<{ assignmentId: string }>;
}) {
  const { assignmentId } = await params;
  return <AssignmentWorkbench key={assignmentId} assignmentId={assignmentId} />;
}
