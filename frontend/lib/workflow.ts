import type { CV } from "./types";
import type { ATSAnalysis } from "./ats";
export interface Workflow {
  id: string;
  version: number;
  data: {
    status: string; source: CV; draft: CV; digest: string;
    before_ats: ATSAnalysis; after_ats: ATSAnalysis;
    suggestions?: {suggestions: unknown; notice: string};
  };
}
/** The UI binds consent to the exact server version; editing always clears it. */
export function canApprove(workflow: Workflow | null, edited: CV | null, confirmed: boolean) {
  return Boolean(workflow && edited && confirmed && workflow.data.status === "awaiting_review"
    && JSON.stringify(workflow.data.draft) === JSON.stringify(edited));
}
