# CLAUDE.md — Frontend

This file provides guidance for the `frontend/` directory of the charger-sim-ocpp project.

## Key Libraries

- **Data fetching:** TanStack React Query — all server state goes through Query hooks in `src/api/`
- **Forms:** React Hook Form + Zod + `@hookform/resolvers` — all forms use this stack
- **UI components:** shadcn/ui (Radix UI primitives) in `src/components/ui/`
- **Styling:** Tailwind CSS with CSS variable semantic tokens (defined in `index.css`)
- **Routing:** React Router v6
- **Notifications:** Sonner toasts (not alerts or custom modals)
- **Icons:** Lucide React exclusively
- **Charts:** Recharts

## Navigation and Layout Rules (from .cursor/rules)

**Route hierarchy:**
```
/                                    → LocationList
/location/:locationId                → LocationDetail
/location/:locationId/charger/:id    → ChargerDetail
```

**Page structure template:**
```tsx
<div className="min-h-screen bg-background">
  <div className="max-w-6xl mx-auto p-6">
    <Breadcrumbs />
    {/* header row */}
    {/* main content */}
  </div>
</div>
```

**Tabs vs Dialogs:**
- Use **tabs** for related content sections on a detail page (preserves context, avoids navigation)
- Use **dialogs** only for short forms (create entity) or destructive confirmations
- `ChargerDetail` uses tabs: Configuration, Logs, Transactions, Scenarios

## Component Conventions

- **Shared status components:** `StatusBadge`, `ConnectionBadge`, `OcppStatusChip`, `PowerTypeChip` — use these rather than inline conditionals
- **Cards:** `LocationCard`, `ChargerCard` for entity summaries
- **`cn()` utility** (`src/lib/utils.ts`) for conditional className merging
- **shadcn/ui** for all primitives — do not install other component libraries

## API Client Pattern

Each resource has a file in `src/api/` exporting React Query hooks:

```typescript
// Example pattern
export function useChargers(locationId: string) {
  return useQuery({ queryKey: ['chargers', locationId], queryFn: () => fetchChargers(locationId) });
}

export function useCreateCharger() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createCharger,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['chargers'] }),
  });
}
```

After mutations, invalidate related query keys. Show success/error feedback via `toast()` from Sonner.

## Form Pattern

```typescript
const form = useForm<FormSchema>({ resolver: zodResolver(schema), defaultValues });

// In JSX:
<Form {...form}>
  <FormField control={form.control} name="field" render={({ field }) => (
    <FormItem>
      <FormLabel>Label</FormLabel>
      <FormControl><Input {...field} /></FormControl>
      <FormMessage />
    </FormItem>
  )} />
</Form>
```

## Theming

- CSS variables defined in `index.css` — use semantic tokens (`bg-background`, `text-foreground`, `border`, etc.) not raw colors
- Font: Inter (body), JetBrains Mono (code/monospace)
- Do not hardcode color values; extend theme via CSS variables
