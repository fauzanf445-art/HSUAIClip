from clipper import run_project, ConsoleUI, SetupEngine

def main():
    ConsoleUI.print_banner()

    try:
        setup = SetupEngine()
        setup.run_system_check()

        url = ConsoleUI.get_user_url()
        if not url: return
        
        result_dir = run_project(url)
        
        ConsoleUI.show_completion(result_dir)

    except KeyboardInterrupt:
        print("\n👋 Dibatalkan pengguna.")
    except Exception as e:
        ConsoleUI.show_error("Terjadi kesalahan fatal", e)

if __name__ == "__main__":
    main()