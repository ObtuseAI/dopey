import { useMemo, useState } from "react";
import { EmptyState } from "./Instruments";
import { statusTone } from "../lib/tone";
import { displayLabel, formatScalar } from "../state";
import type { MutationGenealogyState, MutationNode } from "../types";

interface NodePosition { readonly x: number; readonly y: number }

const graphPositions = (mutation: MutationGenealogyState): Readonly<Record<string, NodePosition>> => {
  const families = [...new Set(mutation.nodes.map((node) => node.family))].sort();
  const positions: Record<string, NodePosition> = {};
  families.forEach((family, familyIndex) => {
    const familyNodes = mutation.nodes.filter((node) => node.family === family);
    const roots = familyNodes.filter((node) => node.parentId === null || node.parentId === "");
    const children = familyNodes.filter((node) => node.parentId !== null && node.parentId !== "");
    const y = 65 + familyIndex * (350 / Math.max(families.length - 1, 1));
    roots.forEach((node, index) => { positions[node.nodeId] = { x: 85 + index * 70, y }; });
    children.forEach((node, index) => { positions[node.nodeId] = { x: 225 + index * (700 / Math.max(children.length - 1, 1)), y }; });
  });
  return positions;
};

const shortNode = (nodeId: string): string => nodeId.replace("genome-", "").replace("-spy-fixture-v1", "").replace("-mut-", "/").slice(0, 26);

export const MutationGenealogyPanel = ({ mutation }: { readonly mutation: MutationGenealogyState }) => {
  const [selectedId, setSelectedId] = useState<string | null>(mutation.paretoFrontierIds[0] ?? mutation.nodes[0]?.nodeId ?? null);
  const positions = useMemo(() => graphPositions(mutation), [mutation]);
  const selected = mutation.nodes.find((node) => node.nodeId === selectedId) ?? mutation.nodes[0] ?? null;
  if (mutation.nodes.length === 0) {
    return <EmptyState detail="The mutation explorer did not emit graph nodes." label="GENEALOGY / EMPTY" />;
  }
  return (
    <div className="genealogy-workbench">
      <div className="genealogy-canvas">
        <svg aria-label="Mutation genealogy graph" role="img" viewBox="0 0 1000 460">
          {mutation.edges.map((edge) => {
            const parent = positions[edge.parentId];
            const child = positions[edge.childId];
            return parent === undefined || child === undefined ? null : <path className={`genealogy-edge genealogy-edge--${statusTone(edge.status)}`} d={`M${parent.x + 9},${parent.y} C${parent.x + 70},${parent.y} ${child.x - 70},${child.y} ${child.x - 9},${child.y}`} key={edge.edgeId} />;
          })}
          {mutation.nodes.map((node) => {
            const position = positions[node.nodeId];
            if (position === undefined) {
              return null;
            }
            const isFrontier = mutation.paretoFrontierIds.includes(node.nodeId);
            return (
              <g
                aria-label={`${node.nodeId}: ${node.status}`}
                className={`genealogy-node genealogy-node--${statusTone(node.status)}${selected?.nodeId === node.nodeId ? " is-selected" : ""}${isFrontier ? " is-frontier" : ""}`}
                key={node.nodeId}
                onClick={() => setSelectedId(node.nodeId)}
                onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { setSelectedId(node.nodeId); } }}
                role="button"
                tabIndex={0}
                transform={`translate(${position.x} ${position.y})`}
              >
                <circle r={isFrontier ? 9 : 6} />
                <text x={12} y={3}>{shortNode(node.nodeId)}</text>
              </g>
            );
          })}
        </svg>
      </div>
      {selected === null ? null : <NodeInspector node={selected} frontier={mutation.paretoFrontierIds.includes(selected.nodeId)} />}
    </div>
  );
};

const NodeInspector = ({ node, frontier }: { readonly node: MutationNode; readonly frontier: boolean }) => (
  <aside className="node-inspector">
    <span>SELECTED MUTATION</span>
    <h3>{shortNode(node.nodeId)}</h3>
    <div className={`status-cell status-cell--${statusTone(node.status)}`}>{displayLabel(node.status)}</div>
    <dl>
      <div><dt>FAMILY</dt><dd>{displayLabel(node.family)}</dd></div>
      <div><dt>OPERATOR</dt><dd>{displayLabel(node.mutationType)}</dd></div>
      <div><dt>SCORE</dt><dd>{formatScalar(node.score, 5)}</dd></div>
      <div><dt>DELTA</dt><dd>{formatScalar(node.scoreDelta, 5)}</dd></div>
      <div><dt>PARETO</dt><dd>{frontier ? "DIAGNOSTIC FRONTIER" : "DOMINATED / ROOT"}</dd></div>
    </dl>
    <p>{node.reasons[0] ?? "No branch reason was reported."}</p>
  </aside>
);
