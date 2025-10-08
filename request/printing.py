import usb.core
import usb.util
import platform
from datetime import datetime

def print_queue_slip(queue_number, transaction_type):
    dev = usb.core.find(idVendor=0x0FE6, idProduct=0x811E)

    if dev is None:
        print("Printer not detected. Check USB connection.")
        return

    try:
        if platform.system() != "Windows":
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)

        dev.set_configuration()
        cfg = dev.get_active_configuration()
        intf = cfg[(0, 0)]
        usb.util.claim_interface(dev, intf)

        ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT,
        )

        if not ep_out:
            print("❌ No OUT endpoint found!")
            return

        # Reset and init printer
        ep_out.write(b'\x1b\x40')  # ESC @

        # --- HEADER ---
        ep_out.write(b'\x1b\x61\x01')  # Center align: ESC a 1
        ep_out.write(b'\x1b\x21\x30')  # Bold + Double height and width
        ep_out.write("QueueAU\n".encode('utf-8'))

        ep_out.write(b'\x1b\x21\x00')  # Normal font
        ep_out.write("PHINMA Araullo University's\n".encode('utf-8'))
        ep_out.write("Queue Ticketing System\n\n".encode('utf-8'))


        ep_out.write("--------------------------------\n".encode('utf-8'))
        ep_out.write(b'\n')

        # --- QUEUE NUMBER ---
        ep_out.write(b'\x1d\x21\x11')  # GS ! n (Double height & width)
        ep_out.write(f"{queue_number}\n".encode('utf-8'))
        ep_out.write(b'\x1d\x21\x00')  # Reset

        # --- TRANSACTION TYPE ---
        ep_out.write(f"{transaction_type}\n\n".encode('utf-8'))
        ep_out.write("--------------------------------\n".encode('utf-8'))
        # --- DATE ---
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        ep_out.write(f"{date_str}\n".encode('utf-8'))

        # --- Cut ---
        ep_out.write(b"\n\n\n")
        ep_out.write(b'\x1d\x56\x00')  # Full cut

        print("Slip printed!")

    except Exception as e:
        print("Error printing:", e)

    finally:
        try:
            usb.util.release_interface(dev, 0)
        except Exception:
            pass
        usb.util.dispose_resources(dev)
