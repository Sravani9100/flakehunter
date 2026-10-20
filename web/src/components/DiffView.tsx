export function DiffView({ diff }: { diff: string }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border font-mono text-xs leading-relaxed">
      {diff.split("\n").map((line, i) => {
        let style = "";
        if (line.startsWith("+++") || line.startsWith("---")) style = "font-semibold text-muted";
        else if (line.startsWith("@@")) style = "bg-accent-soft text-accent";
        else if (line.startsWith("+")) style = "bg-pass-soft text-pass";
        else if (line.startsWith("-")) style = "bg-fail-soft text-fail";
        return (
          <div key={i} className={`whitespace-pre px-4 ${style}`}>
            {line || " "}
          </div>
        );
      })}
    </div>
  );
}
