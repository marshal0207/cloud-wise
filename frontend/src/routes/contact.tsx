import { createFileRoute } from "@tanstack/react-router";
import { Mail, MapPin, Phone, LifeBuoy, Loader2, Send } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { PageShell } from "@/components/layout/PageShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { supabase } from "@/integrations/supabase/client";

export const Route = createFileRoute("/contact")({
  head: () => ({
    meta: [
      { title: "Contact CloudWise — Talk to our cloud team" },
      {
        name: "description",
        content:
          "Questions about monitoring your cloud resources, usage or costs? Send the CloudWise team a message and we'll get back to you.",
      },
      { property: "og:title", content: "Contact CloudWise — Talk to our cloud team" },
      {
        property: "og:description",
        content: "Reach the CloudWise team for support with cloud monitoring, usage and cost questions.",
      },
    ],
  }),
  component: ContactPage,
});

const contactSchema = z.object({
  name: z.string().trim().min(2, "Please enter your name").max(100, "Name is too long"),
  email: z.string().trim().email("Enter a valid email address").max(255),
  subject: z.string().trim().min(3, "Please add a subject").max(150, "Subject is too long"),
  message: z.string().trim().min(10, "Message should be at least 10 characters").max(1000),
});

type FormState = z.infer<typeof contactSchema>;

const emptyForm: FormState = { name: "", email: "", subject: "", message: "" };

const details = [
  { icon: Mail, label: "Email", value: "support@cloudwise.app" },
  { icon: Phone, label: "Phone", value: "+91 98765 43210" },
  { icon: MapPin, label: "Location", value: "Bengaluru, Karnataka, India" },
  { icon: LifeBuoy, label: "Support hours", value: "Mon – Fri, 9:00 AM to 6:00 PM IST" },
];

function ContactPage() {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  function update(field: keyof FormState, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
    setErrors((prev) => ({ ...prev, [field]: undefined }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const parsed = contactSchema.safeParse(form);
    if (!parsed.success) {
      const fieldErrors: Partial<Record<keyof FormState, string>> = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0] as keyof FormState;
        if (!fieldErrors[key]) fieldErrors[key] = issue.message;
      }
      setErrors(fieldErrors);
      return;
    }

    setSubmitting(true);
    const { error } = await supabase.from("contact_messages").insert(parsed.data);
    setSubmitting(false);

    if (error) {
      toast.error("Message could not be sent. Please try again.");
      return;
    }

    setForm(emptyForm);
    setSent(true);
    toast.success("Thanks! Your message has been sent.");
  }

  return (
    <PageShell>
      <section className="bg-gradient-soft">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
          <div className="grid gap-10 lg:grid-cols-2 lg:gap-14">
            <div>
              <span className="inline-flex rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                Contact Us
              </span>
              <h1 className="mt-4 text-3xl font-bold tracking-tight sm:text-4xl">Get in Touch</h1>
              <p className="mt-4 max-w-lg leading-relaxed text-muted-foreground">
                Have a question about monitoring your cloud resources, tracking usage or reducing
                estimated costs? Send us a message and a member of the CloudWise team will reply.
              </p>

              <div className="mt-8 grid gap-4 sm:grid-cols-2">
                {details.map((item) => (
                  <Card key={item.label} className="rounded-2xl border-border/70 bg-gradient-card shadow-soft">
                    <CardContent className="flex min-w-0 items-start gap-3 p-5">
                      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
                        <item.icon className="h-5 w-5" />
                      </span>
                      <div className="min-w-0">
                        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          {item.label}
                        </p>
                        <p className="mt-1 break-words text-sm font-medium">{item.value}</p>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>

            <Card className="rounded-3xl border-border/70 shadow-lift">
              <CardContent className="p-6 sm:p-8">
                <h2 className="text-xl font-semibold">Send us a message</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  All fields are required. We usually respond within one business day.
                </p>

                {sent && (
                  <div className="mt-5 rounded-xl border border-success/30 bg-success/10 p-4 text-sm text-foreground">
                    Your message has been received. Thank you for reaching out to CloudWise!
                  </div>
                )}

                <form className="mt-6 space-y-4" onSubmit={handleSubmit} noValidate>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="name">Name</Label>
                      <Input
                        id="name"
                        value={form.name}
                        onChange={(e) => update("name", e.target.value)}
                        placeholder="Your full name"
                        className="rounded-xl"
                      />
                      {errors.name && <p className="text-xs text-destructive">{errors.name}</p>}
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="email">Email</Label>
                      <Input
                        id="email"
                        type="email"
                        value={form.email}
                        onChange={(e) => update("email", e.target.value)}
                        placeholder="you@example.com"
                        className="rounded-xl"
                      />
                      {errors.email && <p className="text-xs text-destructive">{errors.email}</p>}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="subject">Subject</Label>
                    <Input
                      id="subject"
                      value={form.subject}
                      onChange={(e) => update("subject", e.target.value)}
                      placeholder="What is this about?"
                      className="rounded-xl"
                    />
                    {errors.subject && <p className="text-xs text-destructive">{errors.subject}</p>}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="message">Message</Label>
                    <Textarea
                      id="message"
                      rows={5}
                      value={form.message}
                      onChange={(e) => update("message", e.target.value)}
                      placeholder="Tell us a little more…"
                      className="rounded-xl"
                    />
                    {errors.message && <p className="text-xs text-destructive">{errors.message}</p>}
                  </div>

                  <Button
                    type="submit"
                    disabled={submitting}
                    className="w-full rounded-xl bg-gradient-hero shadow-soft transition-shadow hover:shadow-lift"
                  >
                    {submitting ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Sending…
                      </>
                    ) : (
                      <>
                        <Send className="mr-2 h-4 w-4" /> Send Message
                      </>
                    )}
                  </Button>
                </form>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>
    </PageShell>
  );
}