---
name: Apex Discipline
colors:
  surface: '#131313'
  surface-dim: '#131313'
  surface-bright: '#3a3939'
  surface-container-lowest: '#0e0e0e'
  surface-container-low: '#1c1b1b'
  surface-container: '#201f1f'
  surface-container-high: '#2a2a2a'
  surface-container-highest: '#353534'
  on-surface: '#e5e2e1'
  on-surface-variant: '#e4beb4'
  inverse-surface: '#e5e2e1'
  inverse-on-surface: '#313030'
  outline: '#ab8980'
  outline-variant: '#5b4039'
  surface-tint: '#ffb5a1'
  primary: '#ffb5a1'
  on-primary: '#611300'
  primary-container: '#cc3300'
  on-primary-container: '#ffece7'
  inverse-primary: '#b22b00'
  secondary: '#c8c6c5'
  on-secondary: '#313030'
  secondary-container: '#474746'
  on-secondary-container: '#b7b5b4'
  tertiary: '#c6c6c7'
  on-tertiary: '#2f3131'
  tertiary-container: '#6b6d6d'
  on-tertiary-container: '#efeff0'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#ffdbd1'
  primary-fixed-dim: '#ffb5a1'
  on-primary-fixed: '#3c0800'
  on-primary-fixed-variant: '#881f00'
  secondary-fixed: '#e5e2e1'
  secondary-fixed-dim: '#c8c6c5'
  on-secondary-fixed: '#1c1b1b'
  on-secondary-fixed-variant: '#474746'
  tertiary-fixed: '#e2e2e2'
  tertiary-fixed-dim: '#c6c6c7'
  on-tertiary-fixed: '#1a1c1c'
  on-tertiary-fixed-variant: '#454747'
  background: '#131313'
  on-background: '#e5e2e1'
  surface-variant: '#353534'
typography:
  display-lg:
    fontFamily: Archivo Narrow
    fontSize: 72px
    fontWeight: '700'
    lineHeight: 80px
    letterSpacing: -0.04em
  display-lg-mobile:
    fontFamily: Archivo Narrow
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 52px
    letterSpacing: -0.04em
  headline-xl:
    fontFamily: Archivo Narrow
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
  headline-lg:
    fontFamily: Archivo Narrow
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.1em
  data-point:
    fontFamily: JetBrains Mono
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
spacing:
  base: 8px
  xs: 4px
  sm: 12px
  md: 24px
  lg: 48px
  xl: 80px
  gutter: 24px
  margin: 32px
---

## Brand & Style

The design system is engineered for high-performance fitness and personal development, embodying a "Modern Spartan" ethos. The brand personality is disciplined, elite, and uncompromising. It targets high-achievers who value efficiency, physical dominance, and mental fortitude.

The visual style is a fusion of **Industrial Minimalism** and **High-Contrast Boldness**. It rejects the soft, approachable trends of consumer apps in favor of a raw, "built-for-purpose" aesthetic. 

Key stylistic pillars:
- **Precision:** Mathematical alignment and rigorous grid adherence.
- **Intensity:** High-contrast visuals that demand attention and drive action.
- **Tactile Grit:** Usage of subtle noise textures on dark surfaces to simulate magnesium chalk or industrial steel.
- **Aggressive Whitespace:** Large gaps are not for "breathability," but to emphasize the importance of the remaining content.

## Colors

This design system utilizes a high-contrast, dark-mode-first palette to evoke a focused, cinematic gym environment.

- **Primary (Burnt Crimson):** A high-energy, aggressive red used exclusively for primary actions, progress indicators, and critical alerts.
- **Secondary (Charcoal):** The foundation of the UI, providing a sophisticated, industrial backdrop that reduces eye strain during late-night or early-morning sessions.
- **Tertiary (Stark White):** Used for maximum legibility of content and headers.
- **Neutral (Obsidian):** The deepest black for background layers to create infinite depth and emphasize the "Modern Spartan" atmosphere.

Action states should use a slightly desaturated version of the primary color for hover, and a brightened version for active/pressed states.

## Typography

Typography is a tool for command and clarity. We utilize a three-font system:

1.  **Headline (Archivo Narrow):** A condensed, powerful sans-serif. Use all-caps for all headers to project authority and strength.
2.  **Body (Inter):** The workhorse. Chosen for its exceptional legibility during high-intensity activity.
3.  **Data/Labels (JetBrains Mono):** Monospaced fonts are used for metrics (reps, sets, weight, time). This reinforces the "high-performance/technical" nature of the training.

**Rules:**
- All headers `H1` through `H4` must be uppercase.
- Tracking (letter-spacing) should be tightened on large display type and opened up on monospaced labels.

## Layout & Spacing

The layout is built on a rigid **12-column fixed grid** for desktop and a **4-column fluid grid** for mobile. 

**Spacing Philosophy:**
- Use an **8px linear scale**.
- Padding inside components should be tight (8px or 16px) to maintain a "compressed" and "dense" athletic feel.
- Margins between sections should be expansive (80px+) to isolate different phases of a workout or data set.

**Breakpoints:**
- Mobile: 0 - 599px (Margins: 16px)
- Tablet: 600px - 1023px (Margins: 32px)
- Desktop: 1024px+ (Max container width: 1200px)

## Elevation & Depth

This design system eschews soft shadows and traditional depth. Instead, it uses **Tonal Layering** and **Hard Borders**.

- **Level 0 (Background):** Pure Obsidian (#0D0D0D).
- **Level 1 (Cards/Surface):** Charcoal (#1A1A1A).
- **Level 2 (Active/Hover):** Dark Grey (#2A2A2A).

**The "Blade" Edge:**
Instead of shadows, use 1px solid borders to define surfaces. For interactive elements, use a primary-colored border (Burnt Crimson) to indicate focus. Surfaces should feel like machined parts fitting together, not layers floating in space. 

**Texture:**
Apply a 2% grain overlay to Level 1 surfaces to give them a "powder-coated" industrial finish.

## Shapes

The shape language is strictly **Sharp (0px)**. 

Curves suggest comfort and weakness; right angles suggest structure and discipline. This applies to:
- Buttons
- Form Inputs
- Cards
- Progress Bars (use blocks rather than rounded caps)
- Avatars (square crop)

The only exception to the "no curves" rule is the use of circular iconography when strictly necessary for universal recognition (e.g., a play button), though even then, a square housing is preferred.

## Components

### Buttons
- **Primary:** Burnt Crimson background, White text (Uppercase Archivo Narrow). Sharp corners. No shadow.
- **Secondary:** Ghost style. 2px White border, White text.
- **State Change:** On hover, primary buttons shift to a 100% white background with black text—a "flash" of intensity.

### Input Fields
- Background: Obsidian (#0D0D0D).
- Border: 1px Solid Charcoal (#1A1A1A).
- Active State: 1px Solid Burnt Crimson border.
- Text: JetBrains Mono for all numeric input.

### Cards
- No rounded corners.
- Background: #1A1A1A.
- Border: 1px Solid #2A2A2A.
- Use high-contrast, de-saturated photography as card backgrounds where possible, with a 60% black overlay.

### Progress Indicators
- Linear bars only.
- Use segmented blocks (e.g., 10 separate blocks to represent 100%) rather than a continuous smooth fill to represent "steps" or "reps" completed.

### Data Visualizations
- Line charts: Sharp, angular paths. No smoothing/splines.
- Colors: Burnt Crimson for primary metrics, White for benchmarks.