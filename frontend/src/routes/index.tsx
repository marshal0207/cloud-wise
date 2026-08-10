import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ArrowRight,
  BarChart3,
  CircleDollarSign,
  Gauge,
  LineChart,
  Plug,
  Radar,
  Server,
  Sparkles,
} from "lucide-react";

import heroImage from "@/assets/cloudwise-hero.jpg";
import { PageShell } from "@/components/layout/PageShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "CloudWise — Smart Cloud Management, Made Simple" },
      {
        name: "description",
        content:
          "CloudWise helps you monitor cloud resources, understand usage, track performance and manage cloud costs from one simple dashboard.",
      },
      { property: "og:title", content: "CloudWise — Smart Cloud Management, Made Simple" },
      {
        property: "og:description",
        content:
          "Monitor cloud resources, analyse usage, track performance and stay aware of cloud costs with CloudWise.",
      },
    ],
  }),
  component: Index,
});

const features = [
  {
    icon: Radar,
    title: "Cloud Resource Monitoring",
    body: "Monitor important cloud resources and see their current status at a glance.",
  },
  {
    icon: BarChart3,
    title: "Usage Analytics",
    body: "Understand resource usage through simple charts and clear statistics.",
  },
  {
    icon: CircleDollarSign,
    title: "Cost Awareness",
    body: "Track estimated cloud usage and spot areas of unnecessary consumption.",
  },
  {
    icon: Gauge,
    title: "Performance Insights",
    body: "View basic performance information and identify potential issues early.",
  },
];

const steps = [
  { icon: Plug, title: "Connect / Add Cloud Resources", body: "Bring your servers, databases and storage into one workspace." },
  { icon: Server, title: "Monitor Your Resources", body: "See live status, regions and utilisation for everything you run." },
  { icon: LineChart, title: "Analyze Usage", body: "Read usage trends and cost distribution with simple charts." },
  { icon: Sparkles, title: "Make Better Decisions", body: "Scale down idle resources and keep cloud spend predictable." },
];

function Index() {
  return (
    <PageShell>
      {/* Hero */}
      <section className="bg-gradient-soft">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:py-24">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
              <Sparkles className="h-3.5 w-3.5" /> Cloud monitoring made human
            </span>
            <h1 className="mt-5 text-4xl font-bold leading-[1.1] tracking-tight sm:text-5xl">
              Smart Cloud Management, <span className="text-gradient">Made Simple</span>
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
              CloudWise helps you monitor cloud resources, understand how they are being used, track
              performance and stay on top of cloud costs — all from one clean, easy-to-read dashboard.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button
                asChild
                size="lg"
                className="rounded-xl bg-gradient-hero shadow-soft transition-shadow hover:shadow-lift"
              >
                <Link to="/signup">
                  Get Started <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="rounded-xl">
                <Link to="/dashboard">Explore Dashboard</Link>
              </Button>
            </div>
            <dl className="mt-10 grid max-w-md grid-cols-3 gap-4 text-center">
              {[
                { label: "Resource types", value: "4+" },
                { label: "Regions tracked", value: "Global" },
                { label: "Setup time", value: "< 1 min" },
              ].map((stat) => (
                <div key={stat.label} className="rounded-2xl border border-border/70 bg-card p-3 shadow-soft">
                  <dt className="text-xs text-muted-foreground">{stat.label}</dt>
                  <dd className="mt-1 text-sm font-bold">{stat.value}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="relative">
            <div className="absolute -inset-6 -z-10 rounded-[2.5rem] bg-gradient-hero opacity-10 blur-2xl" />
            <img
              src={heroImage}
              alt="CloudWise dashboard showing cloud resource usage charts and a server rack"
              width={1280}
              height={960}
              className="w-full rounded-3xl border border-border/60 bg-card shadow-lift"
            />
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
        <div className="max-w-2xl">
          <h2 className="text-3xl font-bold tracking-tight">Why CloudWise?</h2>
          <p className="mt-3 text-muted-foreground">
            Everything you need to keep an eye on your cloud environment — without the complexity of
            a full enterprise platform.
          </p>
        </div>

        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((feature) => (
            <Card
              key={feature.title}
              className="rounded-2xl border-border/70 bg-gradient-card shadow-soft transition-all hover:-translate-y-1 hover:shadow-lift"
            >
              <CardContent className="p-6">
                <span className="grid h-11 w-11 place-items-center rounded-xl bg-primary/10 text-primary">
                  <feature.icon className="h-5 w-5" />
                </span>
                <h3 className="mt-4 font-semibold">{feature.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{feature.body}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="border-y border-border bg-secondary/40">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
          <div className="max-w-2xl">
            <h2 className="text-3xl font-bold tracking-tight">How It Works</h2>
            <p className="mt-3 text-muted-foreground">
              Four straightforward steps from raw cloud resources to confident decisions.
            </p>
          </div>

          <ol className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map((step, index) => (
              <li key={step.title} className="rounded-2xl border border-border/70 bg-card p-6 shadow-soft">
                <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
                  <span className="text-xs font-bold uppercase tracking-widest text-primary">
                    Step {index + 1}
                  </span>
                  <step.icon className="h-5 w-5 shrink-0 text-muted-foreground" />
                </div>
                <h3 className="mt-3 font-semibold">{step.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{step.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Final CTA */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
        <div className="overflow-hidden rounded-3xl bg-gradient-hero px-6 py-14 text-center shadow-lift sm:px-12">
          <h2 className="mx-auto max-w-2xl text-2xl font-bold leading-snug text-primary-foreground sm:text-3xl">
            Take control of your cloud environment with CloudWise.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm text-primary-foreground/80">
            Create your free account and get a working monitoring dashboard in under a minute.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button asChild size="lg" variant="secondary" className="rounded-xl">
              <Link to="/signup">
                Get Started <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="rounded-xl bg-transparent text-primary-foreground hover:bg-primary-foreground/10">
              <Link to="/contact">Contact Us</Link>
            </Button>
          </div>
        </div>
      </section>
    </PageShell>
  );
}
