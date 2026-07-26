import { InstrumentPanel } from "../components/Instruments";
import { DatasetTable } from "../components/DatasetTable";
import { PageHeader } from "../components/PageHeader";
import { formatExactTimestamp } from "../state";
import type { DopeySnapshot } from "../types";

export const OrganismsView = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => (
  <div className="secondary-view">
    <PageHeader index="05" thesis="Temporary research assemblies, their adversaries, and the hypotheses they are permitted to test." timestamp={snapshot.observatory.generatedUtc} timestampText={formatExactTimestamp(snapshot.observatory.generatedUtc)} title="Research organisms" />
    <div className="organism-view-grid">
      <InstrumentPanel className="" code="O-31" meta={`${snapshot.observatory.agents.length} RECORDS`} title="Active composition">
        <DatasetTable emptyLabel="AGENTS / NONE REPORTED" rows={snapshot.observatory.agents} />
      </InstrumentPanel>
      <InstrumentPanel className="" code="O-32" meta={`${snapshot.observatory.shadowGuards.length} GUARDS`} title="Shadow perimeter">
        <DatasetTable emptyLabel="SHADOWS / NONE REPORTED" rows={snapshot.observatory.shadowGuards} />
      </InstrumentPanel>
      <InstrumentPanel className="organism-view-grid__hypotheses" code="O-33" meta={`${snapshot.observatory.hypotheses.length} HYPOTHESES`} title="Competing hypotheses">
        <DatasetTable emptyLabel="HYPOTHESES / NONE REPORTED" rows={snapshot.observatory.hypotheses} />
      </InstrumentPanel>
    </div>
  </div>
);
