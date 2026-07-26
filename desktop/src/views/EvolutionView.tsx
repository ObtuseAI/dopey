import { InstrumentPanel } from "../components/Instruments";
import { DatasetTable } from "../components/DatasetTable";
import { MutationGenealogyPanel } from "../components/MutationGenealogyPanel";
import { PageHeader } from "../components/PageHeader";
import { displayLabel, formatExactTimestamp, formatScalar } from "../state";
import type { DopeySnapshot } from "../types";

export const EvolutionView = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => (
  <div className="secondary-view">
    <PageHeader index="08" thesis="Candidate lineage remains isolated from protected truth and execution surfaces; every rejected branch and trial remains visible." timestamp={snapshot.observatory.generatedUtc} timestampText={formatExactTimestamp(snapshot.observatory.generatedUtc)} title="Evolution archive" />
    <div className="evolution-grid">
      <InstrumentPanel className="evolution-grid__graph" code="E-60" meta={`${snapshot.evidence.mutation.nodeCount ?? 0} NODES / ${snapshot.evidence.mutation.edgeCount ?? 0} EDGES`} title="Mutation genealogy">
        <MutationGenealogyPanel mutation={snapshot.evidence.mutation} />
      </InstrumentPanel>
      <InstrumentPanel className="evolution-grid__candidates" code="E-51" meta={`${snapshot.observatory.evolutionCandidates.length} CANDIDATES`} title="Challenger population">
        <DatasetTable emptyLabel="CANDIDATES / NONE REPORTED" rows={snapshot.observatory.evolutionCandidates} />
      </InstrumentPanel>
      <InstrumentPanel className="" code="E-52" meta={displayLabel(snapshot.metacognition.primaryControl)} title="Selection field">
        <div className="selection-field">
          <div><span>KNOWLEDGE BOUNDARY</span><strong>{displayLabel(snapshot.metacognition.knowledgeBoundary)}</strong></div>
          <div><span>RESEARCH UTILITY</span><strong>{formatScalar(snapshot.metacognition.researchUtility, 3)}</strong></div>
          <div><span>EXPECTED INFORMATION GAIN</span><strong>{formatScalar(snapshot.metacognition.expectedInformationGain, 3)}</strong></div>
          <div><span>MUTATION AVAILABLE</span><strong>{snapshot.researchCore.mutationAvailable === null ? "UNKNOWN" : snapshot.researchCore.mutationAvailable ? "YES" : "NO"}</strong></div>
        </div>
      </InstrumentPanel>
      <InstrumentPanel className="" code="E-53" meta="PROTECTED" title="Promotion boundary">
        <div className="promotion-stack">
          {[
            "EXPERIMENTAL",
            "SHADOW ONLY",
            "REPLAY VALIDATED",
            "HELD-OUT VALIDATED",
            "CALIBRATED",
            "RESEARCH APPROVED",
          ].map((stage, index) => <div key={stage}><span>{String(index).padStart(2, "0")}</span><strong>{stage}</strong><i /></div>)}
        </div>
      </InstrumentPanel>
      <InstrumentPanel className="evolution-grid__budgets" code="E-54" meta={`${snapshot.evidence.mutation.mutationAttemptCount ?? 0} RECORDED ATTEMPTS`} title="Family search budget">
        <div className="family-budget-ledger">
          {snapshot.evidence.mutation.familyBudgets.map((budget) => (
            <div key={budget.family}>
              <strong>{displayLabel(budget.family)}</strong>
              <span>{budget.attemptCount ?? "—"} ATTEMPTS</span>
              <i><b style={{ width: `${Math.round((budget.allocationShare ?? 0) * 100)}%` }} /></i>
              <em>{budget.concentrationAlert === true ? "CONCENTRATED" : `${Math.round((budget.allocationShare ?? 0) * 100)}%`}</em>
            </div>
          ))}
        </div>
      </InstrumentPanel>
    </div>
  </div>
);
