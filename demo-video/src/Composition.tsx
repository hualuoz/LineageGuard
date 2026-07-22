import {
  AbsoluteFill,
  Composition,
  Easing,
  Img,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
} from "remotion";

const colors = {
  paper: "#f3f5f2",
  ink: "#132c3f",
  muted: "#61727d",
  cyan: "#bfe5e8",
  amber: "#f2b544",
  red: "#be443c",
  white: "#fcfdfb",
};

const ease = Easing.bezier(0.16, 1, 0.3, 1);

const Frame: React.FC<React.PropsWithChildren<{ label: string }>> = ({ label, children }) => (
  <AbsoluteFill className="frame">
    <div className="topline">
      <div className="wordmark">LINEAGEGUARD</div>
      <div className="context">{label} · DATAHUB CONTEXT</div>
    </div>
    <div className="scene">{children}</div>
  </AbsoluteFill>
);

const Opening: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Frame label="MERGE GATE">
      <div className="opening">
        <div
          className="kicker"
          style={{
            opacity: interpolate(frame, [0, 20], [0, 1], {
              extrapolateRight: "clamp",
              easing: ease,
            }),
          }}
        >
          A DATAHUB MCP MERGE-GATE AGENT
        </div>
        <h1
          style={{
            opacity: interpolate(frame, [10, 35], [0, 1], {
              extrapolateRight: "clamp",
              easing: ease,
            }),
            translate: `0 ${interpolate(frame, [10, 35], [60, 0], {
              extrapolateRight: "clamp",
              easing: ease,
            })}px`,
          }}
        >
          Trace the blast radius
          <br />
          <span>before merge.</span>
        </h1>
      </div>
    </Frame>
  );
};

const Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const strike = interpolate(frame, [95, 135], [0, 100], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });
  return (
    <Frame label="THE FAILURE MODE">
      <div className="statement-scene">
        <div className="kicker">SYNTACTICALLY VALID ≠ SAFE</div>
        <h2>A migration can pass review<br />and still break production.</h2>
        <div className="consumer-row">
          {["DASHBOARDS", "ML FEATURES", "DATA CONTRACTS"].map((item, index) => (
            <div
              className="consumer"
              key={item}
              style={{
                opacity: interpolate(frame, [25 + index * 16, 45 + index * 16], [0, 1], {
                  extrapolateRight: "clamp",
                }),
                translate: `${interpolate(frame, [25 + index * 16, 45 + index * 16], [-40, 0], {
                  extrapolateRight: "clamp",
                  easing: ease,
                })}px 0`,
              }}
            >
              {item}
              <div className="strike" style={{ width: `${strike}%` }} />
            </div>
          ))}
        </div>
      </div>
    </Frame>
  );
};

const Migration: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Frame label="PROPOSED SQL">
      <div className="code-scene">
        <div className="code-heading">
          <div>
            <div className="kicker">ONE LINE. UNKNOWN CONSEQUENCES.</div>
            <h2>What does this actually touch?</h2>
          </div>
          <div className="file-label">migration_042.sql</div>
        </div>
        <div
          className="code-window"
          style={{
            opacity: interpolate(frame, [15, 35], [0, 1], { extrapolateRight: "clamp" }),
            scale: interpolate(frame, [15, 45], [0.97, 1], {
              extrapolateRight: "clamp",
              easing: ease,
            }),
          }}
        >
          <span className="line-number">01</span>
          <span><b>ALTER TABLE</b> analytics.customer_orders</span>
          <span className="line-number">02</span>
          <span><b>DROP COLUMN</b> <mark>email</mark>;</span>
          <div
            className="cursor"
            style={{
              opacity: interpolate(frame % 30, [0, 14, 15, 29], [1, 1, 0, 0]),
            }}
          />
        </div>
        <div
          className="question"
          style={{
            opacity: interpolate(frame, [100, 125], [0, 1], { extrapolateRight: "clamp" }),
          }}
        >
          Code alone cannot answer that.
        </div>
      </div>
    </Frame>
  );
};

const Metadata: React.FC = () => {
  const frame = useCurrentFrame();
  const items = [
    ["MCP · GET_ENTITIES", "Owner + governance"],
    ["MCP · LIST_SCHEMA_FIELDS", "email · VARCHAR · PII"],
    ["MCP · GET_LINEAGE", "ml.churn_features · 1 hop"],
    ["MCP · SAVE_DOCUMENT", "Approved decisions only"],
  ];
  return (
    <Frame label="METADATA IN THE LOOP">
      <div className="metadata-scene">
        <div className="kicker">LINEAGEGUARD CALLS DATAHUB MCP</div>
        <h2>Bring catalog context<br />into the decision.</h2>
        <div className="metadata-stack">
          {items.map(([label, value], index) => (
            <div
              className="metadata-row"
              key={label}
              style={{
                opacity: interpolate(frame, [30 + index * 24, 50 + index * 24], [0, 1], {
                  extrapolateRight: "clamp",
                }),
                translate: `${interpolate(frame, [30 + index * 24, 50 + index * 24], [80, 0], {
                  extrapolateRight: "clamp",
                  easing: ease,
                })}px 0`,
              }}
            >
              <span>{label}</span><strong>{value}</strong>
            </div>
          ))}
        </div>
      </div>
    </Frame>
  );
};

const LiveDemo: React.FC = () => {
  const frame = useCurrentFrame();
  const blockOpacity = interpolate(frame, [105, 125], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const editOpacity = Math.min(
    interpolate(frame, [105, 125], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }),
    interpolate(frame, [245, 265], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }),
  );
  const passOpacity = interpolate(frame, [245, 265], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const pointerProgress = interpolate(frame, [135, 220], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });
  const caption =
    frame < 105
      ? ["01 · REAL LOCAL APP", "Unsafe migration is blocked with DataHub evidence"]
      : frame < 245
        ? ["02 · EDIT THE SQL", "Replace the destructive drop with an additive change"]
        : ["03 · RERUN THE GATE", "PASS WITH CHECKS · risk 0 · merge can continue"];

  return (
    <AbsoluteFill className="live-demo">
      <Img
        className="live-shot"
        src={staticFile("live-console-block.png")}
        style={{ opacity: blockOpacity }}
      />
      <Img
        className="live-shot"
        src={staticFile("live-console-edit.png")}
        style={{ opacity: editOpacity }}
      />
      <Img
        className="live-shot"
        src={staticFile("live-console-pass.png")}
        style={{ opacity: passOpacity }}
      />
      <div className="live-proof">LIVE APPLICATION · LOCALHOST · 2026-07-22</div>
      <div className="live-caption">
        <span>{caption[0]}</span>
        <strong>{caption[1]}</strong>
      </div>
      {frame >= 105 && frame < 265 ? (
        <div
          className="live-pointer"
          style={{
            left: interpolate(pointerProgress, [0, 1], [510, 552]),
            top: interpolate(pointerProgress, [0, 1], [330, 824]),
          }}
        >
          <div
            className="click-ring"
            style={{
              opacity: interpolate(frame, [215, 225, 245], [0, 1, 0], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }),
              scale: interpolate(frame, [215, 245], [0.4, 2.3], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }),
            }}
          />
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

const Verdict: React.FC = () => {
  const frame = useCurrentFrame();
  const lineWidth = interpolate(frame, [65, 120], [0, 100], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });
  return (
    <Frame label="BLAST-RADIUS TRACE">
      <div className="verdict-scene">
        <div className="verdict-top">
          <div
            className="stamp"
            style={{
              opacity: interpolate(frame, [10, 30], [0, 1], { extrapolateRight: "clamp" }),
              scale: interpolate(frame, [10, 35], [1.3, 1], {
                extrapolateRight: "clamp",
                easing: Easing.bezier(0.34, 1.56, 0.64, 1),
              }),
              rotate: "-4deg",
            }}
          >BLOCK</div>
          <div className="risk"><strong>75</strong><span>/ 100 RISK</span></div>
        </div>
        <div className="lineage-rail">
          <div className="node"><span>DATASET</span><strong>customer_orders</strong></div>
          <div className="connector"><div style={{ width: `${lineWidth}%` }} /></div>
          <div className="node danger"><span>CHANGED FIELD</span><strong>email</strong></div>
          <div className="connector"><div style={{ width: `${lineWidth}%` }} /></div>
          <div className="node"><span>1 HOP</span><strong>ml.churn_features</strong></div>
        </div>
        <div className="finding-line">CRITICAL · PII field has an active downstream consumer</div>
      </div>
    </Frame>
  );
};

const Ending: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Frame label="SAFE ROLLOUT">
      <div className="ending">
        <div className="kicker">NOT JUST A WARNING</div>
        <h2>Turn metadata into<br />a migration plan.</h2>
        <div className="steps">
          {["ADD + BACKFILL", "MIGRATE CONSUMERS", "VERIFY LINEAGE", "REMOVE SAFELY"].map(
            (step, index) => (
              <div
                className="step"
                key={step}
                style={{
                  opacity: interpolate(frame, [25 + index * 18, 45 + index * 18], [0, 1], {
                    extrapolateRight: "clamp",
                  }),
                }}
              >
                <span>{String(index + 1).padStart(2, "0")}</span>{step}
              </div>
            ),
          )}
        </div>
        <div
          className="repo"
          style={{
            opacity: interpolate(frame, [185, 220], [0, 1], { extrapolateRight: "clamp" }),
            translate: `0 ${interpolate(frame, [185, 220], [35, 0], {
              extrapolateRight: "clamp",
              easing: ease,
            })}px`,
          }}
        >
          OPEN SOURCE · APACHE-2.0
          <strong>github.com/hualuoz/LineageGuard</strong>
        </div>
      </div>
    </Frame>
  );
};

const LineageGuardDemo: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: colors.paper, color: colors.ink }}>
    <Sequence durationInFrames={150}><Opening /></Sequence>
    <Sequence from={150} durationInFrames={210}><Problem /></Sequence>
    <Sequence from={360} durationInFrames={300}><Migration /></Sequence>
    <Sequence from={660} durationInFrames={300}><Metadata /></Sequence>
    <Sequence from={960} durationInFrames={420}><LiveDemo /></Sequence>
    <Sequence from={1380} durationInFrames={300}><Verdict /></Sequence>
    <Sequence from={1680} durationInFrames={300}><Ending /></Sequence>
  </AbsoluteFill>
);

export const MyComposition: React.FC = () => (
  <Composition
    id="LineageGuardDemo"
    component={LineageGuardDemo}
    durationInFrames={1980}
    fps={30}
    width={1920}
    height={1080}
  />
);
