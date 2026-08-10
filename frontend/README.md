# CloudWise Insights

Build a modern, professional, responsive full-stack web application called "CloudWise".

PROJECT OVERVIEW:

CloudWise is a cloud management and monitoring platform designed to help users monitor, understand, and manage their cloud resources, usage, performance, and costs through a simple dashboard.

The goal is to create a clean academic/project-level website that looks professional and realistic, but is not unnecessarily complex.

TECH STACK:

- Frontend: React + Vite

- Styling: Tailwind CSS

- Backend: Supabase

- Database: PostgreSQL through Supabase

- Authentication: Supabase Authentication

- Use reusable React components

- Make the entire website responsive for desktop, tablet, and mobile.

DESIGN STYLE:

- Modern SaaS/cloud-computing dashboard aesthetic

- Clean and minimal UI

- Professional blue/purple cloud-themed color palette

- White/light background with subtle gradients

- Rounded cards and buttons

- Soft shadows

- Clear typography

- Simple cloud/server/data visualization elements

- Use Lucide icons or another clean icon library

- Add subtle hover effects and smooth transitions

- Avoid excessive animations

- The website should look like a real cloud management product rather than a basic college website.

MAIN NAVIGATION:

Create a consistent navbar across the website with:

Logo:

CloudWise

Navigation:

- Home

- Dashboard

- Contact Us

Right side:

- Login / Sign Up button

- If the user is logged in, show a small user/profile menu and Logout option.

PAGES:

1. HOME PAGE

Create a visually strong landing page.

Hero section:

- Heading: "Smart Cloud Management, Made Simple"

- Supporting text explaining that CloudWise helps users monitor cloud resources, understand usage, track performance, and manage cloud costs.

- Primary CTA: "Get Started"

- Secondary CTA: "Explore Dashboard"

- Add a modern cloud/server illustration or dashboard-style visual.

Add a "Why CloudWise?" section with 3–4 feature cards:

- Cloud Resource Monitoring

  Monitor important cloud resources and their current status.

- Usage Analytics

  Understand resource usage through simple charts and statistics.

- Cost Awareness

  Track estimated cloud usage and identify areas of unnecessary consumption.

- Performance Insights

  View basic performance information and identify potential issues.

Add a simple "How It Works" section:

1. Connect / Add Cloud Resources

2. Monitor Your Resources

3. Analyze Usage

4. Make Better Decisions

Add a final CTA section:

"Take control of your cloud environment with CloudWise."

Footer:

- CloudWise logo/name

- Short description

- Quick links

- Contact Us

- Copyright

2. LOGIN / SIGN UP PAGE

Create a modern authentication page.

Login form:

- Email

- Password

- Login button

- Remember me

- Forgot password

- Link to Sign Up

Sign Up form:

- Full Name

- Email

- Password

- Confirm Password

- Create Account button

Use Supabase Authentication for actual login and registration.

Requirements:

- Show proper validation messages.

- Show loading state while authenticating.

- Show success/error messages.

- After successful login, redirect to Dashboard.

- Logout should work properly.

- Protect the Dashboard route so unauthenticated users cannot access it.

3. DASHBOARD PAGE

This is the main application page after login.

Create a clean cloud monitoring dashboard.

Top section:

- "Welcome to CloudWise"

- Small description

- Current date/time or last updated information.

Summary cards:

- Total Resources

- Active Resources

- Cloud Usage

- Estimated Cost

Add charts:

- Cloud Resource Usage over time

- Cost/Usage distribution

- Resource status distribution

Use realistic sample/demo data initially.

Add a "Cloud Resources" table containing:

- Resource Name

- Resource Type

- Status

- Usage

- Region

- Estimated Cost

- Last Updated

Example resources:

- Web Server

- Database Server

- Storage Bucket

- Application Server

Status should visually indicate:

- Active

- Warning

- Inactive

Add a small "Recent Activity" section showing recent cloud-related events.

IMPORTANT:

Keep the dashboard at a reasonable academic-project level. Do NOT create an overly complicated enterprise cloud management system.

4. CONTACT US PAGE

Create a professional Contact Us page.

Left side:

- Heading: "Get in Touch"

- Short description

- Email

- Phone

- Location

- Support information

Right side:

Contact form with:

- Name

- Email

- Subject

- Message

- Send Message button

When the form is submitted:

- Validate required fields.

- Store the contact message in a Supabase database table called "contact_messages".

- Show a success message after submission.

BACKEND / DATABASE:

Use Supabase for a lightweight backend.

Create these database tables:

1. profiles

Fields:

- id

- full_name

- email

- created_at

2. cloud_resources

Fields:

- id

- user_id

- resource_name

- resource_type

- status

- usage

- region

- estimated_cost

- last_updated

3. contact_messages

Fields:

- id

- name

- email

- subject

- message

- created_at

Use Supabase Row Level Security appropriately.

Users should only be able to access their own cloud resource data.

DASHBOARD DATA:

For the initial version, use realistic demo data if no cloud provider API is connected.

Do NOT integrate AWS, Azure, or Google Cloud APIs yet.

The architecture should however be organized so that real cloud APIs can be integrated later.

FUNCTIONAL REQUIREMENTS:

- Working navigation between all pages

- Working Login

- Working Sign Up

- Working Logout

- Protected Dashboard route

- Working Contact Us form

- Supabase database integration

- Responsive design

- Form validation

- Loading states

- Error handling

- Empty states where appropriate

- Reusable components

- Clean folder structure

- No broken links

- No placeholder buttons that appear functional but do nothing

RESPONSIVE DESIGN:

The website must work properly on:

- Desktop

- Laptop

- Tablet

- Mobile

On mobile:

- Convert navbar into a hamburger menu.

- Dashboard cards should stack vertically.

- Tables should become horizontally scrollable or responsive cards.

- Forms should use full width.

UI DETAILS:

Use:

- Modern cards

- Consistent spacing

- Rounded corners

- Professional typography

- Subtle gradients

- Cloud/server icons

- Charts using a suitable React chart library

- Toast notifications where appropriate

- Loading skeletons/spinners where useful

Do not:

- Overcrowd the interface

- Use excessive animations

- Add unnecessary pages

- Add unnecessary enterprise features

- Add payment systems

- Add real cloud provider integrations

- Add complex admin panels

FINAL PAGE STRUCTURE:

/              → Home

/login         → Login

/signup        → Sign Up

/dashboard     → Protected Dashboard

/contact       → Contact Us

If possible, keep Login and Sign Up as one authentication experience while still supporting both routes.

IMPORTANT:

Build the complete frontend and lightweight backend/database integration in one project.

Before finishing:

1. Make sure the application runs without errors.

2. Make sure all routes work.

3. Make sure authentication works.

4. Make sure the dashboard is protected.

5. Make sure Contact Us stores messages in Supabase.

6. Make sure the UI is responsive.

7. Make sure the design is consistent across all pages.

8. Make the final result polished enough for a college project demonstration.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/87a61099-6c69-4100-ad8f-05970c3ee7e3).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
