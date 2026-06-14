export default function FeatureCards() {
  const features = [
    {
      title: "Multi-Agent Orchestration",
      desc: "Planner, Research, Analysis, Verification, Conflict Detection, Synthesis, and Evaluation agents.",
    },
    {
      title: "Claim-to-Source Traceability",
      desc: "Every important claim is mapped back to supporting evidence and sources.",
    },
    {
      title: "Enterprise-Ready Verification",
      desc: "Designed for audit-ready, source-backed answers instead of simple chatbot responses.",
    },
  ];

  return (
    <div className="mt-6 grid gap-4 sm:grid-cols-3">
      {features.map((item) => (
        <div key={item.title} className="card p-5">
          <h3 className="text-sm font-bold text-slate-800">{item.title}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-500">{item.desc}</p>
        </div>
      ))}
    </div>
  );
}