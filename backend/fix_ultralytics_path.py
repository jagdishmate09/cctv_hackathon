"""
Script to fix Ultralytics directory issue on Windows
Run this if you get the error: Cannot create a file when that file already exists
"""
import os
import sys

def fix_ultralytics_path():
    """Fix the Ultralytics config path issue on Windows"""
    try:
        # Get the Ultralytics config directory path
        home = os.path.expanduser("~")
        ultralytics_path = os.path.join(home, "AppData", "Roaming", "Ultralytics")
        
        print(f"Checking path: {ultralytics_path}")
        
        # Check if path exists and what it is
        if os.path.exists(ultralytics_path):
            if os.path.isfile(ultralytics_path):
                print(f"Found FILE at path (should be directory): {ultralytics_path}")
                print("Removing file...")
                try:
                    os.remove(ultralytics_path)
                    print("OK: File removed successfully!")
                except PermissionError:
                    print("ERROR: Permission denied.")
                    print("Please close any programs that might be using this file, or run as administrator.")
                    return False
                except Exception as e:
                    print(f"ERROR: Error removing file: {e}")
                    return False
            elif os.path.isdir(ultralytics_path):
                print(f"OK: Directory already exists correctly: {ultralytics_path}")
                return True
        
        # Try to create the directory
        print("Creating Ultralytics directory...")
        try:
            os.makedirs(ultralytics_path, exist_ok=True)
            print(f"OK: Directory created successfully: {ultralytics_path}")
            return True
        except FileExistsError:
            # This means it exists as a file, try to remove it
            print("ERROR: Path exists as a file, attempting to remove...")
            try:
                if os.path.isfile(ultralytics_path):
                    os.remove(ultralytics_path)
                    print("File removed, creating directory...")
                    os.makedirs(ultralytics_path, exist_ok=True)
                    print("OK: Directory created after removing file")
                    return True
                else:
                    print("ERROR: Path exists but is neither file nor directory")
                    return False
            except Exception as e:
                print(f"ERROR: Could not remove file: {e}")
                print("\nPlease manually delete this file:")
                print(f"  {ultralytics_path}")
                print("Then run this script again or restart your computer.")
                return False
        except Exception as e:
            print(f"ERROR: Error creating directory: {e}")
            return False
            
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Ultralytics Path Fixer for Windows")
    print("=" * 60)
    print()
    
    success = fix_ultralytics_path()
    
    print()
    if success:
        print("=" * 60)
        print("SUCCESS: Fix completed successfully!")
        print("You can now run: python app.py")
        print("=" * 60)
    else:
        print("=" * 60)
        print("FAILED: Fix failed. Please check the errors above.")
        print("=" * 60)
        print("\nManual fix:")
        print("1. Close all Python programs")
        print("2. Navigate to: C:\\Users\\JagdishMate\\AppData\\Roaming\\")
        print("3. Delete the file named 'Ultralytics' (if it exists)")
        print("4. Run this script again")
        print("=" * 60)
        sys.exit(1)
