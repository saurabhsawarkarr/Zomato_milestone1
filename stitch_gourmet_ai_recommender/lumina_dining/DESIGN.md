---
name: Lumina Dining
colors:
  surface: '#10141a'
  surface-dim: '#10141a'
  surface-bright: '#353940'
  surface-container-lowest: '#0a0e14'
  surface-container-low: '#181c22'
  surface-container: '#1c2026'
  surface-container-high: '#262a31'
  surface-container-highest: '#31353c'
  on-surface: '#dfe2eb'
  on-surface-variant: '#e4bebc'
  inverse-surface: '#dfe2eb'
  inverse-on-surface: '#2d3137'
  outline: '#ab8987'
  outline-variant: '#5b403f'
  surface-tint: '#ffb3b1'
  primary: '#ffb3b1'
  on-primary: '#680011'
  primary-container: '#ff535a'
  on-primary-container: '#5b000e'
  inverse-primary: '#bb162c'
  secondary: '#ffb690'
  on-secondary: '#552100'
  secondary-container: '#ec6a06'
  on-secondary-container: '#4a1c00'
  tertiary: '#71d7cf'
  on-tertiary: '#003734'
  tertiary-container: '#32a099'
  on-tertiary-container: '#00302d'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#ffdad8'
  primary-fixed-dim: '#ffb3b1'
  on-primary-fixed: '#410007'
  on-primary-fixed-variant: '#92001c'
  secondary-fixed: '#ffdbca'
  secondary-fixed-dim: '#ffb690'
  on-secondary-fixed: '#341100'
  on-secondary-fixed-variant: '#783200'
  tertiary-fixed: '#8ef4eb'
  tertiary-fixed-dim: '#71d7cf'
  on-tertiary-fixed: '#00201e'
  on-tertiary-fixed-variant: '#00504c'
  background: '#10141a'
  on-background: '#dfe2eb'
  surface-variant: '#31353c'
typography:
  display-lg:
    fontFamily: Outfit
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Outfit
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Outfit
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
  headline-md:
    fontFamily: Outfit
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
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
  label-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 12px
  md: 24px
  lg: 48px
  xl: 80px
  container-margin: 20px
  gutter: 16px
---

## Brand & Style
The design system is engineered for a premium, AI-driven culinary discovery experience. The brand personality is sophisticated yet energetic, positioning the app as an elite concierge that understands high-end gastronomy. The target audience consists of food enthusiasts and urban explorers who value both aesthetic precision and technological intelligence.

The visual style is a refined **Glassmorphism**. It utilizes multi-layered depth, background blurs, and luminous accents to create a sense of high-tech elegance. The interface feels immersive, as if content is floating over a deep, infinite void, punctuated by vibrant data points and interactive "glow" states.

## Colors
The palette is anchored by a deep charcoal-navy background (`#0d1117`), providing a high-contrast foundation for the glass effects. The primary visual driver is a "Cinder Gradient" moving from a rich red to a vibrant orange, used exclusively for primary actions, AI highlights, and ranking indicators.

- **Primary/Secondary:** The gradient captures the heat of the kitchen and the energy of discovery.
- **Neutral:** Surfaces use varying opacities of white (5% to 12%) over the dark background to create the "frosted" effect.
- **Semantic Colors:** Success is represented by a crisp emerald, while alerts use the primary red without the orange transition to maintain urgency.

## Typography
The typography system pairs the geometric modernism of **Outfit** with the functional clarity of **Inter**.

- **Headlines (Outfit):** Used for restaurant names, category titles, and AI insights. Its circular motifs echo the rounded UI elements.
- **Body (Inter):** Used for descriptions, reviews, and technical data. It ensures high legibility against dark, translucent backgrounds.
- **Styling:** Headings should use tight letter-spacing to feel "contained" and premium. Labels use slightly increased tracking for clarity at small sizes.

## Layout & Spacing
This design system utilizes a **Fluid Grid** with a 12-column structure for desktop and a 4-column structure for mobile. 

- **Grid Logic:** Content is organized into modular glass "tiles." 
- **Rhythm:** An 8px base unit governs all dimensions.
- **Safe Areas:** Mobile views require a 20px side margin to prevent glass edge-clash with the device frame.
- **Adaptation:** On mobile, complex side-by-side card layouts stack vertically, while filters move into a horizontal scrolling pill-bar.

## Elevation & Depth
Depth is communicated through **Optical Layering** rather than traditional drop shadows.

- **Level 1 (Background):** Deep Navy (`#0d1117`).
- **Level 2 (Glass Cards):** White at 5% opacity with a `backdrop-filter: blur(12px)`. These have a 1px border at 12% white opacity to define the edge.
- **Level 3 (Floating Elements):** Popovers or Modals use 10% white opacity and a `backdrop-filter: blur(20px)`.
- **Glow Effects:** Interactive elements (like the active rank badge or primary button) emit a soft, 20px-radius outer glow using the primary gradient colors at 30% opacity.

## Shapes
The shape language is consistently **Rounded**. 

- **Cards:** Use a 1rem (`rounded-lg`) corner radius to soften the technical aesthetic.
- **Interactive Elements:** Buttons and tags use a full pill-shape (`rounded-xl` or 100px) to contrast against the rectangular layout of the grid.
- **Borders:** Every glass surface must have a subtle 1px inner stroke to simulate the edge of a physical glass pane.

## Components
### Buttons & Inputs
- **Primary Button:** Pill-shaped, featuring the Cinder Gradient. On hover, it triggers a pulse animation and increases glow intensity.
- **Input Fields:** Semi-transparent glass with a 1px border. On focus, the border transitions to the primary gradient.

### Glass Cards
- Feature a `hover: translate-y(-4px)` lift effect.
- Content within cards should have high internal padding (24px) to emphasize the "airy" glass feel.

### Rank Badges & Tags
- **Rank Badges:** Gold, Silver, and Bronze badges use metallic gradients with a glass overlay.
- **Pill Tags:** Used for cuisine types (e.g., "Italian," "Vegan"). These are semi-transparent with a solid 1px border.

### AI & Feedback
- **Pulse Animations:** Used for AI "thinking" states and loading indicators, utilizing a soft breathing effect on the accent gradient.
- **Range Sliders:** Custom tracks using the gradient for the active range, with a frosted glass thumb/handle.

### Motion
- **Staggered Entrances:** List items and restaurant cards should slide in from the bottom with a 50ms stagger between items.