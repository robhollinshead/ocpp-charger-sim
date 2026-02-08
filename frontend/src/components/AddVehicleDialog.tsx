import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import type { VehicleCreate } from '@/types/ocpp';
import { useCreateVehicle } from '@/api/vehicles';
import { toast } from 'sonner';

const addVehicleSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  idTag: z.string().min(1, 'idTag is required'),
  battery_capacity_kWh: z.number().positive('Battery capacity must be positive'),
});

type AddVehicleFormValues = z.infer<typeof addVehicleSchema>;

interface AddVehicleDialogProps {
  locationId: string | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddVehicleDialog({
  locationId,
  open,
  onOpenChange,
}: AddVehicleDialogProps) {
  const createVehicle = useCreateVehicle(locationId);
  const form = useForm<AddVehicleFormValues>({
    resolver: zodResolver(addVehicleSchema),
    defaultValues: {
      name: '',
      idTag: '',
      battery_capacity_kWh: 75,
    },
  });

  async function onSubmit(values: AddVehicleFormValues) {
    if (!locationId) return;
    try {
      await createVehicle.mutateAsync(values as VehicleCreate);
      toast.success('Vehicle created');
      form.reset({ name: '', idTag: '', battery_capacity_kWh: 75 });
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create vehicle');
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add vehicle</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. Test Vehicle" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="idTag"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>idTag</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. ABC12345" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="battery_capacity_kWh"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Battery capacity (kWh)</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={0.01}
                      step="any"
                      value={field.value}
                      onChange={(e) => {
                        const v = parseFloat(e.target.value);
                        field.onChange(isNaN(v) ? 0 : v);
                      }}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={createVehicle.isPending || !locationId}>
                {createVehicle.isPending ? 'Creating…' : 'Add vehicle'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
