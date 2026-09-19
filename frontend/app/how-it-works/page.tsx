import type { Metadata } from "next";
import s from "./how.module.css";

export const metadata: Metadata = {
  title: "How DoorLens works",
  description: "A plain-language guide to uploading train telemetry and reading DoorLens results.",
};

const steps = [
  { n: "1", h: "Pick a subsystem", p: "Choose Door to analyse a door-motor recording, or ACV to find the leaking air-conditioning car on a train." },
  { n: "2", h: "Drop in your file", p: "Drag the recording onto the page. Door takes a .csv; ACV takes the .xlsx workbook (or a .csv). Nothing is installed and nothing leaves the service." },
  { n: "3", h: "Read the answer", p: "You get a plain result first, then the evidence behind it: charts, a car-by-car table, and how much confidence to place in it." },
  { n: "4", h: "Download it", p: "Export the prediction file in the exact format maintenance or the judges expect, or a single predictions.zip." },
];

export default function HowItWorks() {
  return (
    <main className={s.page}>
      <a className={s.back} href="/">← Back to the app</a>
      <header className={s.hero}>
        <h1>What DoorLens does, and how to use it.</h1>
        <p>Trains stream thousands of sensor readings every minute. DoorLens turns two of those streams into a short, checkable answer, so a person knows where to look first.</p>
      </header>

      <section aria-label="Steps" className={s.steps}>
        {steps.map((x) => (
          <div key={x.n} className={s.step}>
            <span>{x.n}</span>
            <h2>{x.h}</h2>
            <p>{x.p}</p>
          </div>
        ))}
      </section>

      <section className={s.grid}>
        <article className={s.card}>
          <h2>Door: is each open/close healthy?</h2>
          <p className={s.tag}>Input · door-motor recording (.csv)</p>
          <p>The recording is one long stream with idle gaps. DoorLens finds each open or close movement, then labels it <b>Normal</b> or <b>Abnormal resistance</b> by comparing its motor current, voltage and door position with what normal movements look like.</p>
          <ul>
            <li><b>Result:</b> a list of movements with start/end times and a label.</li>
            <li><b>Evidence:</b> the movement&apos;s current against a normal reference band.</li>
            <li><b>What-if:</b> &ldquo;Challenge this result&rdquo; nudges the recording (for example current +5%) to show whether the label is stable.</li>
          </ul>
        </article>
        <article className={s.card}>
          <h2>ACV: which car is leaking?</h2>
          <p className={s.tag}>Input · train telemetry workbook (.xlsx)</p>
          <p>A refrigerant leak makes a car&apos;s air conditioning cool poorly, so its cabin sits warmer than its own target. DoorLens measures that gap for all 8 cars and ranks them against each other, most suspicious first.</p>
          <ul>
            <li><b>Result:</b> the most likely car, plus the full ranking.</li>
            <li><b>Evidence:</b> a time chart of every car&apos;s temperature gap, and a table of the numbers.</li>
            <li><b>Lead size:</b> how far ahead the top car is. A small lead means inspect the top 2 or 3.</li>
          </ul>
        </article>
      </section>

      <section className={s.card}>
        <h2>A worked example</h2>
        <p>An operator uploads <code>acv_case.xlsx</code>. DoorLens answers <b>Car 03</b> with a large lead, ranking <code>03 › 02 › 01 › 07 › 08 › 04 › 06 › 05</code>. The chart shows Car 03&apos;s cabin running about 1 °C above its setpoint while the others sit around 0.3 °C. The engineer opens the ACV unit on Car 03 first, and Car 02 second if the first check finds nothing.</p>
      </section>

      <section className={s.grid}>
        <article className={s.card}>
          <h2>Where it helps</h2>
          <ul>
            <li>Triage: decide which car or door to inspect first.</li>
            <li>Spot a sensor that has died (it is ranked last, not flagged).</li>
            <li>Explain a result to someone else with the charts and table.</li>
          </ul>
        </article>
        <article className={s.card}>
          <h2>What it does not do</h2>
          <ul>
            <li>It is not a safety system and never controls a train or door.</li>
            <li>Scores are relative comparisons, not probabilities of failure.</li>
            <li>The ACV method assumes exactly one leaking car in the file, so it always names a top car, even on a healthy train.</li>
            <li>Door labels do not say why a door is stiff (roller, motor, obstruction).</li>
          </ul>
        </article>
      </section>

      <p className={s.foot}>Built and checked on the NebulaX hackathon datasets only. See the methodology panel in the Door view for the saved evaluation and limitations.</p>
    </main>
  );
}
